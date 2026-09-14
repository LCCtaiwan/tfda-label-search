const form = document.querySelector("#search-form");
const allInput = document.querySelector("#all-terms");
const anyInput = document.querySelector("#any-terms");
const excludeInput = document.querySelector("#exclude-terms");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const loadMoreButton = document.querySelector("#load-more");
const dataVersion = document.querySelector("#data-version");

let pagefindPromise;
let synonymsPromise;
let catalogPromise;
let activeSearch;
let searchGeneration = 0;
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

async function catalog() {
  catalogPromise ??= fetch("./data/catalog.json")
    .then((response) => {
      if (!response.ok) throw new Error("藥品目錄讀取失敗");
      return response.json();
    })
    .then((payload) => {
      if (payload.schema_version !== 1 || !Array.isArray(payload.documents)) {
        throw new Error("藥品目錄格式錯誤");
      }
      return payload.documents;
    });
  return catalogPromise;
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

async function loadDocument(meta) {
  const documentPath = safeDocumentPath(meta.document_path);
  if (!documentPath) throw new Error("結果缺少安全的章節資料路徑");
  if (!documentCache.has(documentPath)) {
    documentCache.set(documentPath, fetch(`./${documentPath}`).then((response) => {
      if (!response.ok) throw new Error("章節原文讀取失敗");
      return response.json();
    }));
  }
  return documentCache.get(documentPath);
}

function addText(parent, tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value;
  parent.append(element);
  return element;
}

function normalized(value) {
  return String(value ?? "").normalize("NFKC").toLocaleLowerCase("zh-TW");
}

function expanded(term, synonymMap) {
  return synonymMap.get(term) ?? [term];
}

function includesGroup(text, term, synonymMap) {
  const haystack = normalized(text);
  return expanded(term, synonymMap).some((item) => haystack.includes(normalized(item)));
}

function matches(text, query, synonymMap) {
  if (!query.all.every((term) => includesGroup(text, term, synonymMap))) return false;
  if (query.any.length && !query.any.some((term) => includesGroup(text, term, synonymMap))) return false;
  if (query.excluded.some((term) => includesGroup(text, term, synonymMap))) return false;
  return true;
}

function metadataText(source) {
  return [
    source.drug_name_zh,
    source.drug_name_en,
    source.license_no,
    ...(source.ingredients ?? []).flatMap((item) => [item.name, item.amount]),
    ...(source.nhi_items ?? []).flatMap((item) => [item.code, item.atc_code, item.benefit_chapter]),
  ].filter(Boolean).join(" ");
}

function sectionText(section) {
  return [...(section.path ?? []), section.title, section.search_text, section.content_text]
    .filter(Boolean).join(" ");
}

function createSearchState(found, query, synonymMap) {
  return {
    candidates: [...found.values()],
    candidateIndex: 0,
    current: null,
    sectionIndex: 0,
    metadataChecked: false,
    displayed: 0,
    query,
    synonymMap,
    exhausted: false,
    seenDocuments: new Set(),
  };
}

async function collectNext(state, limit = 50) {
  const entries = [];
  while (entries.length < limit && state.candidateIndex < state.candidates.length) {
    if (!state.current) {
      const record = await state.candidates[state.candidateIndex].data();
      const meta = record.meta ?? {};
      const recordId = meta.record_id || meta.document_path;
      if (recordId && state.seenDocuments.has(recordId)) {
        state.candidateIndex += 1;
        continue;
      }
      if (recordId) state.seenDocuments.add(recordId);
      const source = await loadDocument(meta);
      state.current = { record, meta, source };
      state.sectionIndex = 0;
      state.metadataChecked = false;
    }

    const { record, meta, source } = state.current;
    if (!state.metadataChecked) {
      state.metadataChecked = true;
      if (matches(metadataText(source), state.query, state.synonymMap)) {
        entries.push({ record, meta, source, section: null });
      }
      if (entries.length >= limit) break;
    }

    const sections = source.sections ?? [];
    while (entries.length < limit && state.sectionIndex < sections.length) {
      const section = sections[state.sectionIndex];
      state.sectionIndex += 1;
      if (matches(sectionText(section), state.query, state.synonymMap)) {
        entries.push({ record, meta, source, section });
      }
    }

    if (state.sectionIndex >= sections.length) {
      state.current = null;
      state.candidateIndex += 1;
    }
  }
  state.exhausted = state.candidateIndex >= state.candidates.length && !state.current;
  return entries;
}

function appendEntries(entries) {
  for (const { record, meta, source, section } of entries) {
    const ingredientText = meta.ingredients || (source.ingredients ?? []).map((item) => item.name).filter(Boolean).join("、");
    const nhiCodeText = meta.nhi_codes || (source.nhi_items ?? []).map((item) => item.code).filter(Boolean).join("、");
    const atcText = meta.atc_codes || [...new Set((source.nhi_items ?? []).map((item) => item.atc_code).filter(Boolean))].join("、");
    const card = document.createElement("article");
    addText(card, "h2", "drug-name", meta.drug_name_zh || source.drug_name_zh || meta.drug_name_en || source.drug_name_en || "未命名藥品");
    addText(card, "p", "english-name", meta.drug_name_en || source.drug_name_en || "");
    const versionText = source.source_kind === "metadata_only"
      ? "尚無結構化電子仿單文字"
      : `仿單第 ${meta.version || source.version || "?"} 版｜${meta.approved_at || source.approved_at || "日期未提供"}`;
    addText(card, "p", "metadata", `${meta.license_no || source.license_no || "無藥證"}｜${versionText}`);
    if (ingredientText) addText(card, "p", "metadata", `成分：${ingredientText}`);
    if (nhiCodeText) addText(card, "p", "metadata", `健保碼：${nhiCodeText}${atcText ? `｜ATC：${atcText}` : ""}`);
    addText(card, "h3", "section-title", section ? (section.path ?? []).join(" › ") || section.title || "未標示章節" : "藥品資料");
    addText(card, "p", "excerpt", section ? (section.search_text || section.content_text || "本章沒有文字內容").slice(0, 260) : record.plain_excerpt || "藥品資料命中");

    if (section) {
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
          original.textContent = section.content_text || section.search_text || "本章沒有文字內容";
        } catch (error) {
          original.textContent = error instanceof Error ? error.message : "原文載入失敗";
        }
      });
      card.append(details);
    }

    const official = safeOfficialUrl(meta.official_url || source.official_url);
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

async function showNext(state, generation) {
  loadMoreButton.disabled = true;
  status.textContent = state.displayed ? "正在載入更多…" : "搜尋中…";
  const entries = await collectNext(state);
  if (generation !== searchGeneration) return;
  appendEntries(entries);
  state.displayed += entries.length;
  loadMoreButton.disabled = false;
  loadMoreButton.hidden = state.exhausted;
  status.textContent = state.exhausted
    ? `找到 ${state.displayed} 筆結果。`
    : `已顯示 ${state.displayed} 筆，尚有更多結果。`;
}

async function runSearch(event) {
  event.preventDefault();
  const all = terms(allInput.value);
  const any = terms(anyInput.value);
  const excluded = terms(excludeInput.value);
  const supplied = [...all, ...any, ...excluded];
  const generation = ++searchGeneration;
  activeSearch = null;
  results.replaceChildren();
  loadMoreButton.hidden = true;

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
    const [engine, synonymMap, catalogDocuments] = await Promise.all([pagefind(), synonyms(), catalog()]);
    const allGroups = await Promise.all(all.map((item) => searchGroup(engine, item, synonymMap)));
    const anyGroups = await Promise.all(any.map((item) => searchGroup(engine, item, synonymMap)));
    let found = allGroups.length ? allGroups.reduce(intersect) : union(anyGroups);
    if (allGroups.length && anyGroups.length) found = intersect(found, union(anyGroups));
    const metadataMatches = new Map(catalogDocuments
      .filter((document) => matches(metadataText(document), { all, any, excluded }, synonymMap))
      .map((document) => [`catalog:${document.record_id}`, {
        data: async () => ({ meta: document.meta, plain_excerpt: "藥品資料命中" }),
      }]));
    found = union([metadataMatches, found]);

    activeSearch = createSearchState(found, { all, any, excluded }, synonymMap);
    await showNext(activeSearch, generation);
  } catch (error) {
    if (generation !== searchGeneration) return;
    status.textContent = error instanceof Error ? error.message : "搜尋失敗";
  }
}

form.addEventListener("submit", runSearch);
loadMoreButton.addEventListener("click", () => {
  if (!activeSearch || activeSearch.exhausted) return;
  showNext(activeSearch, searchGeneration).catch((error) => {
    status.textContent = error instanceof Error ? error.message : "載入更多結果失敗";
    loadMoreButton.disabled = false;
  });
});

fetch("./data/manifest.json", { cache: "no-cache" })
  .then((response) => {
    if (!response.ok) throw new Error("版本資料讀取失敗");
    return response.json();
  })
  .then((manifest) => {
    const date = String(manifest.data_retrieved_at || manifest.built_at || "").slice(0, 10) || "日期未提供";
    const count = Number.isInteger(manifest.document_count) ? manifest.document_count.toLocaleString("zh-TW") : "?";
    const fingerprint = /^[a-f0-9]{64}$/u.test(manifest.dataset_sha256 ?? "")
      ? manifest.dataset_sha256.slice(0, 12)
      : "未提供";
    dataVersion.textContent = `資料版本：${date}｜${count} 份｜指紋 ${fingerprint}`;
  })
  .catch(() => {
    dataVersion.textContent = "資料版本：無法讀取，請勿據此判斷資料已更新。";
  });

const params = new URLSearchParams(location.search);
allInput.value = params.get("q") ?? "";
if (allInput.value) form.requestSubmit();
