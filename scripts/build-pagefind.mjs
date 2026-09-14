import { createHash } from "node:crypto";
import { cp, mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import * as pagefind from "pagefind";

const GENERATED_MARKER = ".tfda-label-search-generated";

function parseArgs(argv) {
  const options = { inputs: [], output: "site" };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--input") options.inputs.push(argv[++index]);
    else if (value === "--output") options.output = argv[++index];
    else throw new Error(`未知參數：${value}`);
  }
  if (!options.inputs.length || options.inputs.some((item) => !item)) {
    throw new Error("至少需要一個 --input 結構化仿單 JSON");
  }
  if (!options.output) throw new Error("--output 不可為空");
  return options;
}

function stableId(...parts) {
  return createHash("sha256").update(parts.join("\u001f"), "utf8").digest("hex").slice(0, 20);
}

function plain(value) {
  return typeof value === "string" ? value.trim() : "";
}

function officialUrl(licenseNo) {
  return `https://mcp.fda.gov.tw/im_detail_1/${encodeURIComponent(licenseNo)}`;
}

function stringList(value) {
  return Array.isArray(value) ? [...new Set(value.map(plain).filter(Boolean))] : [];
}

function validatePayload(payload, sourcePath) {
  if (!payload || payload.schema_version !== 1 || !Array.isArray(payload.documents)) {
    throw new Error(`${sourcePath} 不是支援的結構化仿單 JSON`);
  }
  if (payload.document_count !== payload.documents.length) {
    throw new Error(`${sourcePath} 的 document_count 與 documents 數量不同`);
  }
  for (const document of payload.documents) {
    if (!plain(document.license_no) || !Array.isArray(document.sections)) {
      throw new Error(`${sourcePath} 含有缺少藥證或章節的文件`);
    }
  }
}

async function exists(filePath) {
  try {
    await stat(filePath);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function assertReplaceable(outputPath) {
  if (!(await exists(outputPath))) return;
  if (!(await exists(path.join(outputPath, GENERATED_MARKER)))) {
    throw new Error(`拒絕覆蓋未標記為本專案產物的目錄：${outputPath}`);
  }
}

async function build({ inputs, output }) {
  const outputPath = path.resolve(output);
  const tempPath = `${outputPath}.tmp-${process.pid}`;
  await assertReplaceable(outputPath);
  await rm(tempPath, { recursive: true, force: true });
  await mkdir(path.join(tempPath, "data", "documents"), { recursive: true });
  await cp(path.resolve("web"), tempPath, { recursive: true });

  const synonymSource = path.resolve("config", "synonyms.json");
  await cp(synonymSource, path.join(tempPath, "data", "synonyms.json"));

  const { index } = await pagefind.createIndex({
    forceLanguage: "zh",
    keepIndexUrl: true,
    verbose: false,
  });

  const seenDocuments = new Set();
  const catalog = [];
  const sourceInputs = [];
  let documentCount = 0;
  let sectionCount = 0;
  let recordCount = 0;

  for (const input of inputs) {
    const sourcePath = path.resolve(input);
    const sourceText = await readFile(sourcePath, "utf8");
    const payload = JSON.parse(sourceText);
    validatePayload(payload, sourcePath);
    sourceInputs.push({
      name: path.basename(input),
      sha256: createHash("sha256").update(sourceText, "utf8").digest("hex"),
      retrieved_at: plain(payload.retrieved_at),
    });

    for (const document of payload.documents) {
      const documentKey = `${plain(document.license_no)}:${plain(document.version)}`;
      if (seenDocuments.has(documentKey)) throw new Error(`重複仿單版本：${documentKey}`);
      seenDocuments.add(documentKey);
      documentCount += 1;

      const documentId = stableId(documentKey);
      const documentPath = `data/documents/${documentId}.json`;
      const safeDocument = {
        schema_version: 1,
        license_no: plain(document.license_no),
        drug_name_zh: plain(document.drug_name_zh),
        drug_name_en: plain(document.drug_name_en),
        version: plain(document.version),
        approved_at: plain(document.approved_at),
        source_kind: plain(document.source_kind),
        official_url: officialUrl(plain(document.license_no)),
        ingredients: Array.isArray(document.ingredients) ? document.ingredients.map((item) => ({
          name: plain(item?.name ?? item?.ingredient_name),
          amount: plain(item?.amount_description),
        })).filter((item) => item.name) : [],
        nhi_items: Array.isArray(document.nhi_items) ? document.nhi_items.map((item) => ({
          code: plain(item?.code ?? item?.nhi_code),
          atc_code: plain(item?.atc_code),
          benefit_chapter: plain(item?.benefit_chapter),
        })).filter((item) => item.code) : [],
        event_types: stringList(document.event_types),
        sections: document.sections.map((section) => ({
          id: plain(section.id),
          parent_id: plain(section.parent_id),
          level: Number.isInteger(section.level) ? section.level : 1,
          number: plain(section.number),
          title: plain(section.title),
          path: Array.isArray(section.path) ? section.path.map(plain).filter(Boolean) : [],
          content_text: plain(section.content_text),
          search_text: plain(section.search_text),
        })),
      };
      await writeFile(
        path.join(tempPath, documentPath),
        `${JSON.stringify(safeDocument)}\n`,
        "utf8",
      );

      sectionCount += safeDocument.sections.length;
      const documentContent = [
        safeDocument.drug_name_zh,
        safeDocument.drug_name_en,
        safeDocument.license_no,
        safeDocument.ingredients.map((item) => `${item.name} ${item.amount}`).join(" "),
        safeDocument.nhi_items.map((item) => `${item.code} ${item.atc_code} ${item.benefit_chapter}`).join(" "),
        ...safeDocument.sections.map((section) => `${section.path.join(" ")} ${section.search_text}`),
      ].filter(Boolean).join("\n");
      const documentMeta = {
        record_id: documentId,
        title: safeDocument.drug_name_zh || safeDocument.drug_name_en || safeDocument.license_no,
        drug_name_zh: safeDocument.drug_name_zh,
        drug_name_en: safeDocument.drug_name_en,
        license_no: safeDocument.license_no,
        version: safeDocument.version,
        approved_at: safeDocument.approved_at,
        ingredients: safeDocument.ingredients.map((item) => item.name).join("、"),
        nhi_codes: safeDocument.nhi_items.map((item) => item.code).join("、"),
        atc_codes: [...new Set(safeDocument.nhi_items.map((item) => item.atc_code).filter(Boolean))].join("、"),
        document_path: documentPath,
        official_url: safeDocument.official_url,
      };
      catalog.push({
        record_id: documentId,
        document_path: documentPath,
        drug_name_zh: safeDocument.drug_name_zh,
        drug_name_en: safeDocument.drug_name_en,
        license_no: safeDocument.license_no,
        ingredients: safeDocument.ingredients,
        nhi_items: safeDocument.nhi_items,
        meta: documentMeta,
      });
      const { errors } = await index.addCustomRecord({
        url: `./?document=${documentId}`,
        content: documentContent,
        language: "zh",
        meta: {
          ...documentMeta,
          record_type: "document",
        },
        filters: { source_kind: [safeDocument.source_kind || "unknown"] },
      });
      if (errors?.length) {
        throw new Error(`Pagefind 無法加入 ${documentId}：${errors.join("；")}`);
      }
      recordCount += 1;
    }
  }

  const { errors } = await index.writeFiles({ outputPath: path.join(tempPath, "pagefind") });
  if (errors?.length) throw new Error(`Pagefind 索引輸出失敗：${errors.join("；")}`);
  await index.deleteIndex();
  await pagefind.close();

  const manifest = {
    schema_version: 1,
    built_at: new Date().toISOString(),
    data_retrieved_at: sourceInputs.map((item) => item.retrieved_at).filter(Boolean).sort().at(-1) ?? "",
    dataset_sha256: createHash("sha256")
      .update(sourceInputs.map((item) => item.sha256).join("\n"), "utf8")
      .digest("hex"),
    document_count: documentCount,
    section_count: sectionCount,
    record_count: recordCount,
    source_files: inputs.map((item) => path.basename(item)),
    source_inputs: sourceInputs,
  };
  await writeFile(path.join(tempPath, "data", "catalog.json"), `${JSON.stringify({
    schema_version: 1,
    document_count: catalog.length,
    documents: catalog,
  })}\n`, "utf8");
  await writeFile(path.join(tempPath, "data", "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  await writeFile(path.join(tempPath, GENERATED_MARKER), "generated by tfda-label-search\n", "utf8");

  if (await exists(outputPath)) await rm(outputPath, { recursive: true });
  await rename(tempPath, outputPath);
  process.stdout.write(`${JSON.stringify({ output: outputPath, ...manifest })}\n`);
}

try {
  await build(parseArgs(process.argv.slice(2)));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
  await pagefind.close().catch(() => {});
}
