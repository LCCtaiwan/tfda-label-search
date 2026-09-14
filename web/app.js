const form = document.querySelector("#search-form");
const allInput = document.querySelector("#all-terms");
const anyInput = document.querySelector("#any-terms");
const excludeInput = document.querySelector("#exclude-terms");
const status = document.querySelector("#status");
const results = document.querySelector("#results");

let pagefindPromise;
let synonymsPromise;
const documentCache = new Map();

function terms(value) {
  return [...new Set(value.split(/[\s,，;；]+/u).map((item) => item.trim()).filter(Boolean))];
}

function validTerm(value) {
  return [...value].length >= 2;
}

async function pagefind() {
  pagefindPromise ??= import("./pagefind/pagefind.js").then(async (module) => {
    await module.init();
    return module;
  });
  return pagefindPromise;
}

async function synonyms() {
  synonymsPromise ??= fetch("./data/synonyms.json", { cache: "no-cache" })
    .then((response) => {
      if (!response.ok) throw new Error("同義詞資料讀取失敗");
      return response.json();
    })
    .then((payload) => {
      const mapping = new Map();
      for (const entry of payload.entries ?? []) {
        if (entry.reviewed !== true || !Array.isArray(entry.terms)) continue;
        const group = [...new Set(entry.terms.map((item) => String(item).trim()).filter(Boolean))];
        for (const item of group) mapping.set(item, group);
      }
      return mapping;
    });
  return synonymsPromise;
}

async function searchOne(engine, value) {
  const response = await engine.search(value);
  return new Map(response.results.map((result) => [result.id, result]));
}

function union(maps) {
  const output = new Map();
  for (const map of maps) for (const [key, value] of map) output.set(key, value);
  return output;
}

function intersect(left, right) {
  return new Map([...left].filter(([key]) => right.has(key)));
}

async function searchGroup(engine, value, synonymMap) {
  const expanded = synonymMap.get(value) ?? [value];
  return union(await Promise.all(expanded.map((item) => searchOne(engine, item))));
}

function safeDocumentPath(value) {
  return /^data\/documents\/[a-f0-9]{20}\.json$/u.test(value ?? "") ? value : "";
}

function safeOfficialUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "mcp.fda.gov.tw" ? url.href : "";
  } catch {
    return "";
  }
}

async function loadSection(meta) {
  const documentPath = safeDocumentPath(meta.document_path);
  if (!documentPath) throw new Error("結果缺少安全的章節資料路徑");
  if (!documentCache.has(documentPath)) {
    documentCache.set(documentPath, fetch(`./${documentPath}`).then((response) => {
      if (!response.ok) throw new Error("章節原文讀取失敗");
      return response.json();
    }));
  }
  const document = await documentCache.get(documentPath);
  const section = document.sections?.find((item) => item.id === meta.section_id);
  if (!section) throw new Error("找不到對應的章節原文");
  return section;
}

function addText(parent, tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  parent.append(element);
  return element;
}

async function render(found) {
  results.replaceChildren();
  const selected = [...found.values()].slice(0, 50);
  const records = await Promise.all(selected.map((item) => item.data()));
  status.textContent = `找到 ${found.size} 個章節，顯示前 ${records.length} 筆。`;

  for (const record of records) {
    const meta = record.meta ?? {};
    const card = document.createElement("article");
    addText(card, "h2", "drug-name", meta.drug_name_zh || meta.drug_name_en || "未命名藥品");
    addText(card, "p", "english-name", meta.drug_name_en || "");
    addText(card, "p", "metadata", `${meta.license_no || "無藥證"}｜仿單第 ${meta.version || "?"} 版｜${meta.approved_at || "日期未提供"}`);
    addText(card, "h3", "section-title", meta.section_path || meta.section_title || "未標示章節");
    addText(card, "p", "excerpt", record.plain_excerpt || "命中摘要未提供");

    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "查看本章原文";
    const original = document.createElement("pre");
    original.textContent = "展開後載入…";
    details.append(summary, original);
    details.addEventListener("toggle", async () => {
      if (!details.open || details.dataset.loaded) return;
      details.dataset.loaded = "true";
      try {
        const section = await loadSection(meta);
        original.textContent = section.content_text || section.search_text || "本章沒有文字內容";
      } catch (error) {
        original.textContent = error instanceof Error ? error.message : "原文載入失敗";
      }
    });
    card.append(details);

    const official = safeOfficialUrl(meta.official_url);
    if (official) {
      const link = document.createElement("a");
      link.href = official;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "開啟 TFDA 官方電子仿單";
      card.append(link);
    }
    results.append(card);
  }
}

async function runSearch(event) {
  event.preventDefault();
  const all = terms(allInput.value);
  const any = terms(anyInput.value);
  const excluded = terms(excludeInput.value);
  const supplied = [...all, ...any, ...excluded];
  results.replaceChildren();

  if (!all.length && !any.length) {
    status.textContent = "請在 AND 或 OR 至少輸入一個關鍵字。";
    return;
  }
  if (supplied.some((item) => !validTerm(item))) {
    status.textContent = "每個關鍵字至少需要兩個字元。";
    return;
  }

  status.textContent = "搜尋中…";
  try {
    const [engine, synonymMap] = await Promise.all([pagefind(), synonyms()]);
    const allGroups = await Promise.all(all.map((item) => searchGroup(engine, item, synonymMap)));
    const anyGroups = await Promise.all(any.map((item) => searchGroup(engine, item, synonymMap)));
    let found = allGroups.length ? allGroups.reduce(intersect) : union(anyGroups);
    if (allGroups.length && anyGroups.length) found = intersect(found, union(anyGroups));

    const excludedGroups = await Promise.all(excluded.map((item) => searchGroup(engine, item, synonymMap)));
    const rejected = union(excludedGroups);
    found = new Map([...found].filter(([key]) => !rejected.has(key)));
    await render(found);
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "搜尋失敗";
  }
}

form.addEventListener("submit", runSearch);

const params = new URLSearchParams(location.search);
allInput.value = params.get("q") ?? "";
if (allInput.value) form.requestSubmit();
