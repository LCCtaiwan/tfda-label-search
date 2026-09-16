const form = document.querySelector("#search-form");
const allInput = document.querySelector("#all-terms");
const anyInput = document.querySelector("#any-terms");
const excludeInput = document.querySelector("#exclude-terms");
const status = document.querySelector("#status");
const results = document.querySelector("#results");
const loadMoreButton = document.querySelector("#load-more");
const dataVersion = document.querySelector("#data-version");
const coverageSummary = document.querySelector("#coverage-summary");
const freshnessWarning = document.querySelector("#freshness-warning");
const MAX_TERMS = 10;
const MAX_TERM_LENGTH = 80;
const MAX_DATA_AGE_DAYS = 14;
const EVENT_LABELS = Object.freeze({
  recall: "藥品回收資料",
  safety_alert: "藥品安全警訊資料",
  risk_management: "風險管理計畫資料",
  shortage_with_alternative: "藥品短缺資料（有替代品）",
  shortage_without_alternative: "藥品短缺資料（無替代品）",
});

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
  const length = [...value].length;
  return length >= 2 && length <= MAX_TERM_LENGTH;
}

function updateSearchUrl(query) {
  const next = new URL(location.href);
  next.search = "";
  if (query.all.length) next.searchParams.set("q", query.all.join(" "));
  if (query.any.length) next.searchParams.set("any", query.any.join(" "));
  if (query.excluded.length) next.searchParams.set("exclude", query.excluded.join(" "));
  history.replaceState(null, "", next);
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
        for (const item of group) mapping.set(normalized(item), group);
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
  const expanded = synonymMap.get(normalized(value)) ?? [value];
  return union(await Promise.all(expanded.map((item) => searchOne(engine, item))));
}

function safeDocumentPath(value) {
  return /^data\/documents\/[a-f0-9]{20}\.json$/u.test(value ?? "") ? value : "";
}

function safeOfficialUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:"
      && url.hostname === "mcp.fda.gov.tw"
      && !url.username
      && !url.password
      && ["", "443"].includes(url.port)
      ? url.href
      : "";
  } catch {
    return "";
  }
}

function safeEventSourceUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:"
      && url.hostname === "data.fda.gov.tw"
      && !url.username
      && !url.password
      && ["", "443"].includes(url.port)
      ? url.href
      : "";
  } catch {
    return "";
  }
}

function safeNhiUrl(value, allowedHost) {
  try {
    const url = new URL(value);
    return url.protocol === "https:"
      && url.hostname === allowedHost
      && !url.username
      && !url.password
      && ["", "443"].includes(url.port)
      ? url.href
      : "";
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

function validCalendarDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function taipeiToday() {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function showFreshnessWarning(value) {
  const dataDate = String(value ?? "").slice(0, 10);
  const today = taipeiToday();
  if (!validCalendarDate(dataDate) || !validCalendarDate(today)) {
    freshnessWarning.textContent = "注意：無法確認官方資料更新日期。請先到官方來源核對，再用於工作。";
    freshnessWarning.hidden = false;
    return "日期未提供";
  }
  const dayMilliseconds = 24 * 60 * 60 * 1000;
  const ageDays = Math.round(
    (Date.parse(`${today}T00:00:00Z`) - Date.parse(`${dataDate}T00:00:00Z`)) / dayMilliseconds,
  );
  if (ageDays < -1) {
    freshnessWarning.textContent = "注意：官方資料日期晚於今天，日期可能有誤。請先到官方來源核對。";
    freshnessWarning.hidden = false;
  } else if (ageDays > MAX_DATA_AGE_DAYS) {
    freshnessWarning.textContent = `注意：這個網站的官方資料已 ${ageDays} 天沒有更新。請先到官方來源核對，再用於工作。`;
    freshnessWarning.hidden = false;
  } else {
    freshnessWarning.textContent = "";
    freshnessWarning.hidden = true;
  }
  return dataDate;
}

function expanded(term, synonymMap) {
  return synonymMap.get(normalized(term)) ?? [term];
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

function containsPositiveTerm(text, query, synonymMap) {
  return [...query.all, ...query.any].some((term) => includesGroup(text, term, synonymMap));
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
    matchedDocuments: 0,
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
      const documentText = [
        metadataText(source),
        ...(source.sections ?? []).map(sectionText),
      ].join(" ");
      if (!matches(documentText, state.query, state.synonymMap)) {
        state.candidateIndex += 1;
        continue;
      }
      state.matchedDocuments += 1;
      state.current = { record, meta, source };
      state.sectionIndex = 0;
      state.metadataChecked = false;
    }

    const { record, meta, source } = state.current;
    if (!state.metadataChecked) {
      state.metadataChecked = true;
      if (containsPositiveTerm(metadataText(source), state.query, state.synonymMap)) {
        entries.push({ record, meta, source, section: null });
      }
      if (entries.length >= limit) break;
    }

    const sections = source.sections ?? [];
    while (entries.length < limit && state.sectionIndex < sections.length) {
      const section = sections[state.sectionIndex];
      state.sectionIndex += 1;
      if (containsPositiveTerm(sectionText(section), state.query, state.synonymMap)) {
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

    const linkGroup = document.createElement("div");
    linkGroup.className = "resource-links";
    const addOfficialLink = (href, label) => {
      const link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = label;
      linkGroup.append(link);
    };
    const official = safeOfficialUrl(meta.official_url || source.official_url);
    if (official) addOfficialLink(official, "開啟 TFDA 官方電子仿單");
    const rawFileUrls = Array.isArray(source.pdf_urls) ? source.pdf_urls : [];
    const fileUrls = [...new Set(rawFileUrls.map(safeOfficialUrl).filter(Boolean))];
    for (const [index, href] of fileUrls.entries()) {
      const suffix = fileUrls.length > 1 ? ` ${index + 1}` : "";
      addOfficialLink(href, `開啟 TFDA 官方仿單檔案${suffix}`);
    }
    if (linkGroup.childElementCount) card.append(linkGroup);

    const nhiItems = Array.isArray(source.nhi_items)
      ? source.nhi_items.map((item) => ({
        code: String(item?.code ?? "").trim(),
        atcCode: String(item?.atc_code ?? "").trim(),
        benefitChapter: String(item?.benefit_chapter ?? "").trim(),
        specification: String(item?.specification ?? "").trim(),
        price: String(item?.price ?? "").trim(),
        effectiveFrom: String(item?.effective_from ?? "").trim(),
        effectiveUntil: String(item?.effective_until ?? "").trim(),
        company: String(item?.company ?? "").trim(),
        dosageForm: String(item?.dosage_form ?? "").trim(),
        itemUrl: safeNhiUrl(item?.item_url, "lmspiq.fda.gov.tw"),
        ruleUrl: safeNhiUrl(item?.rule_url, "info.nhi.gov.tw"),
      })).filter((item) => item.code)
      : [];
    if (nhiItems.length) {
      const nhiDetails = document.createElement("details");
      nhiDetails.className = "nhi-details";
      const nhiSummary = document.createElement("summary");
      nhiSummary.textContent = `查看健保資料（${nhiItems.length} 筆）`;
      addText(
        nhiDetails,
        "p",
        "nhi-caution",
        "這是資料版本日期以前的健保資料，不代表目前仍給付、支付價仍相同或適用個別情況。",
      );
      const list = document.createElement("ul");
      for (const item of nhiItems) {
        const listItem = document.createElement("li");
        addText(listItem, "strong", "nhi-code", `健保碼：${item.code}`);
        const effectivePeriod = item.effectiveFrom || item.effectiveUntil
          ? `${item.effectiveFrom || "未載明起日"}～${item.effectiveUntil || "未載明迄日"}`
          : "";
        const description = [
          item.atcCode && `ATC：${item.atcCode}`,
          item.specification && `規格：${item.specification}`,
          item.dosageForm && `劑型：${item.dosageForm}`,
          item.price && `支付價：${item.price}`,
          effectivePeriod && `有效期間：${effectivePeriod}`,
          item.company && `藥商：${item.company}`,
          item.benefitChapter && `給付章節：${item.benefitChapter}`,
        ].filter(Boolean).join("｜");
        if (description) addText(listItem, "p", "nhi-description", description);
        const links = document.createElement("div");
        links.className = "resource-links nhi-links";
        if (item.itemUrl) {
          const link = document.createElement("a");
          link.href = item.itemUrl;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "官方藥品資料";
          links.append(link);
        }
        if (item.ruleUrl) {
          const link = document.createElement("a");
          link.href = item.ruleUrl;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = "健保給付規定";
          links.append(link);
        }
        if (links.childElementCount) listItem.append(links);
        list.append(listItem);
      }
      nhiDetails.append(nhiSummary, list);
      card.append(nhiDetails);
    }

    const officialEvents = Array.isArray(source.official_events)
      ? source.official_events.map((event) => ({
        label: EVENT_LABELS[event?.event_type] ?? "",
        publishedOn: String(event?.published_on ?? "").trim(),
        title: String(event?.title ?? "").trim(),
        eventStatus: String(event?.status ?? "").trim(),
        sourceUrl: safeEventSourceUrl(event?.source_url),
      })).filter((event) => event.label && event.sourceUrl)
      : [];
    if (officialEvents.length) {
      const eventDetails = document.createElement("details");
      eventDetails.className = "official-events";
      const eventSummary = document.createElement("summary");
      eventSummary.textContent = `曾出現在 TFDA 其他官方資料（${officialEvents.length} 筆）`;
      addText(
        eventDetails,
        "p",
        "event-caution",
        "這是資料版本日期以前的關聯紀錄，不代表目前仍在回收、警示、風險管理或短缺。",
      );
      const list = document.createElement("ul");
      for (const event of officialEvents) {
        const item = document.createElement("li");
        const description = [
          event.label,
          event.publishedOn,
          event.title,
          event.eventStatus,
        ].filter(Boolean).join("｜");
        addText(item, "span", "event-description", description);
        const link = document.createElement("a");
        link.href = event.sourceUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "TFDA 資料集來源";
        item.append(" ", link);
        list.append(item);
      }
      eventDetails.append(eventSummary, list);
      card.append(eventDetails);
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
  if (state.displayed !== state.matchedDocuments) {
    status.textContent = state.exhausted
      ? `找到 ${state.displayed} 個命中章節，來自 ${state.matchedDocuments} 份仿單。`
      : `已顯示 ${state.displayed} 個命中章節，來自 ${state.matchedDocuments} 份仿單，尚有更多結果。`;
  } else {
    status.textContent = state.exhausted
      ? `找到 ${state.displayed} 筆結果。`
      : `已顯示 ${state.displayed} 筆，尚有更多結果。`;
  }
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
    updateSearchUrl({ all, any, excluded });
    status.textContent = "請在 AND 或 OR 至少輸入一個關鍵字。";
    return;
  }
  if (supplied.some((item) => !validTerm(item))) {
    status.textContent = `每個關鍵字需要 2 到 ${MAX_TERM_LENGTH} 個字元。`;
    return;
  }
  if (supplied.length > MAX_TERMS) {
    status.textContent = `三個欄位合計最多 ${MAX_TERMS} 個關鍵字。`;
    return;
  }

  updateSearchUrl({ all, any, excluded });
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

async function loadJson(path, message) {
  const response = await fetch(path, { cache: "no-cache" });
  if (!response.ok) throw new Error(message);
  return response.json();
}

Promise.all([
  loadJson("./data/manifest.json", "版本資料讀取失敗"),
  loadJson("./data/coverage.json", "涵蓋資料讀取失敗"),
])
  .then(([manifest, coverage]) => {
    const coverageCounts = [
      coverage.searchable_text_documents,
      coverage.metadata_only_documents,
      coverage.metadata_only_with_official_files,
      coverage.metadata_only_without_official_files,
    ];
    if (
      manifest.schema_version !== 1
      || coverage.schema_version !== 1
      || !Number.isInteger(manifest.document_count)
      || coverage.document_count !== manifest.document_count
      || coverageCounts.some((value) => !Number.isInteger(value) || value < 0)
      || coverage.searchable_text_documents + coverage.metadata_only_documents
        !== coverage.document_count
      || coverage.metadata_only_with_official_files
        + coverage.metadata_only_without_official_files !== coverage.metadata_only_documents
    ) {
      throw new Error("版本與涵蓋資料不一致");
    }
    const date = showFreshnessWarning(manifest.data_retrieved_at);
    const count = manifest.document_count.toLocaleString("zh-TW");
    const fingerprint = /^[a-f0-9]{64}$/u.test(manifest.dataset_sha256 ?? "")
      ? manifest.dataset_sha256.slice(0, 12)
      : "未提供";
    dataVersion.textContent = `資料版本：${date}｜${count} 份｜指紋 ${fingerprint}`;
    coverageSummary.textContent = [
      `資料涵蓋：${coverage.searchable_text_documents.toLocaleString("zh-TW")} 份有可搜尋仿單文字`,
      `${coverage.metadata_only_with_official_files.toLocaleString("zh-TW")} 份只有官方檔案連結`,
      `${coverage.metadata_only_without_official_files.toLocaleString("zh-TW")} 份目前沒有仿單文字或檔案`,
    ].join("｜");
  })
  .catch(() => {
    showFreshnessWarning("");
    dataVersion.textContent = "資料版本：無法讀取，請勿據此判斷資料已更新。";
    coverageSummary.textContent = "資料涵蓋：無法讀取，請勿假設資料完整。";
  });

const params = new URLSearchParams(location.search);
allInput.value = params.get("q") ?? params.get("all") ?? "";
anyInput.value = params.get("any") ?? "";
excludeInput.value = params.get("exclude") ?? params.get("not") ?? "";
if (allInput.value || anyInput.value) form.requestSubmit();
