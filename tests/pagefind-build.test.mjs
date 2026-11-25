import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("builds one searchable record per document without publishing raw HTML", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "tfda-pagefind-test-"));
  const output = path.join(temporaryRoot, "site");
  const synonyms = path.join(temporaryRoot, "synonyms.json");

  try {
    await writeFile(synonyms, JSON.stringify({
      schema_version: 1,
      entries: [
        {
          terms: ["孕期", "懷孕"],
          reviewed: true,
          reviewer: "自動測試",
          reviewed_at: "2026-09-15",
        },
        { terms: ["草稿甲", "草稿乙"], reviewed: false },
      ],
    }), "utf8");
    execFileSync(process.execPath, [
      "scripts/build-pagefind.mjs",
      "--input",
      "tests/fixtures/pagefind-search-sample.json",
      "--synonyms",
      synonyms,
      "--output",
      output,
    ], { cwd: root, stdio: "pipe" });

    const manifest = JSON.parse(await readFile(path.join(output, "data", "manifest.json"), "utf8"));
    assert.equal(manifest.document_count, 4);
    assert.equal(manifest.section_count, 7);
    assert.equal(manifest.record_count, 4);
    assert.match(manifest.built_at, /^\d{4}-\d{2}-\d{2}T/u);
    assert.equal(manifest.data_retrieved_at, "2026-09-15T00:00:00Z");
    assert.match(manifest.dataset_sha256, /^[a-f0-9]{64}$/u);
    assert.equal(manifest.source_inputs.length, 1);
    const coverage = JSON.parse(await readFile(path.join(output, "data", "coverage.json"), "utf8"));
    assert.deepEqual(coverage, {
      schema_version: 1,
      document_count: 4,
      searchable_text_documents: 3,
      metadata_only_documents: 1,
    });
    const publishedSynonyms = JSON.parse(
      await readFile(path.join(output, "data", "synonyms.json"), "utf8"),
    );
    assert.equal(publishedSynonyms.entries.length, 1);
    assert.deepEqual(publishedSynonyms.entries[0].terms, ["孕期", "懷孕"]);
    assert.equal(publishedSynonyms.entries[0].reviewer, "自動測試");
    assert.doesNotMatch(JSON.stringify(publishedSynonyms), /草稿/u);

    const documents = await readdir(path.join(output, "data", "documents"));
    assert.equal(documents.length, 4);
    const catalog = JSON.parse(await readFile(path.join(output, "data", "catalog.json"), "utf8"));
    assert.equal(catalog.document_count, 4);
    assert.equal(catalog.documents.length, 4);
    assert.ok(catalog.documents.every((item) => item.record_id && item.document_path));
    assert.ok(catalog.documents.every((item) => item.meta.record_id === item.record_id));
    const metadataOnly = catalog.documents.find(
      (item) => item.license_no === "測試藥證字第000004號",
    );
    const fallbackDocument = JSON.parse(
      await readFile(path.join(output, metadataOnly.document_path), "utf8"),
    );
    assert.equal(fallbackDocument.official_url,
      `https://mcp.fda.gov.tw/im_detail_1/${encodeURIComponent(metadataOnly.license_no)}`);
    assert.equal("pdf_urls" in fallbackDocument, false);
    const eventDocumentMeta = catalog.documents.find(
      (item) => item.license_no === "測試藥證字第000002號",
    );
    const eventDocument = JSON.parse(
      await readFile(path.join(output, eventDocumentMeta.document_path), "utf8"),
    );
    assert.deepEqual(eventDocument.event_types, ["safety_alert"]);
    assert.deepEqual(eventDocument.official_events, [{
      event_type: "safety_alert",
      published_on: "2026-09-01",
      title: "TEST INGREDIENT",
      status: "",
      source_url: "https://data.fda.gov.tw/data/opendata/export/53/json",
    }]);
    const nhiDocumentMeta = catalog.documents.find(
      (item) => item.license_no === "測試藥證字第000001號",
    );
    const nhiDocument = JSON.parse(
      await readFile(path.join(output, nhiDocumentMeta.document_path), "utf8"),
    );
    assert.equal(nhiDocumentMeta.meta.nhi_codes, "A000000001");
    assert.equal(nhiDocument.nhi_items.length, 2);
    assert.deepEqual(nhiDocument.nhi_items[0], {
      code: "A000000001",
      atc_code: "A01AA01",
      benefit_chapter: "1.1",
      specification: "10 MG",
      price: "1.5",
      effective_from: "2026-01-01",
      effective_until: "",
      company: "測試藥商",
      dosage_form: "TABLET",
      item_url: "https://lmspiq.fda.gov.tw/web/DRPIQ/DRPIQ1000Result?licId=01000001",
      rule_url: "https://info.nhi.gov.tw/rule",
    });
    assert.equal(nhiDocument.nhi_items[1].price, "1.4");
    assert.equal(nhiDocument.nhi_items[1].effective_until, "2025-12-31");
    for (const filename of documents) {
      const payload = await readFile(path.join(output, "data", "documents", filename), "utf8");
      assert.doesNotMatch(payload, /<img\b/iu);
      assert.doesNotMatch(payload, /data:image\//iu);
      assert.doesNotMatch(payload, /pdf_urls|official_file|\/test\/000004\.pdf/iu);
    }

    assert.ok((await stat(path.join(output, "pagefind", "pagefind.js"))).isFile());
    assert.ok((await stat(path.join(output, ".tfda-label-search-generated"))).isFile());
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("ignores legacy file links and replaces untrusted official URLs with the license page", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "tfda-pagefind-url-test-"));
  const input = path.join(temporaryRoot, "input.json");
  const output = path.join(temporaryRoot, "site");
  try {
    const payload = JSON.parse(
      await readFile(path.join(root, "tests/fixtures/pagefind-search-sample.json"), "utf8"),
    );
    for (const doc of payload.documents) {
      doc.pdf_urls = ["https://example.com/not-official.pdf"];
      doc.official_url = "https://mcp.fda.gov.tw/test/official-file.pdf";
    }
    // An empty API insert with titles/search terms alone has no searchable insert text.
    const empty = payload.documents[0];
    empty.source_kind = "tfda_structured_insert";
    empty.sections.forEach((section) => { section.content_text = " "; });
    payload.documents[1].source_kind = "no_document";
    await writeFile(input, JSON.stringify(payload), "utf8");
    execFileSync(process.execPath, [
      "scripts/build-pagefind.mjs", "--input", input, "--output", output,
    ], { cwd: root, stdio: "pipe" });
    const coverage = JSON.parse(await readFile(path.join(output, "data/coverage.json"), "utf8"));
    assert.equal(coverage.searchable_text_documents, 1);
    assert.equal(coverage.metadata_only_documents, 3);
    for (const filename of await readdir(path.join(output, "data/documents"))) {
      const text = await readFile(path.join(output, "data/documents", filename), "utf8");
      const doc = JSON.parse(text);
      assert.equal(doc.official_url,
        `https://mcp.fda.gov.tw/im_detail_1/${encodeURIComponent(doc.license_no)}`);
      assert.doesNotMatch(text, /pdf_urls|official-file|example\.com/u);
      if (doc.license_no === empty.license_no) {
        assert.equal(doc.source_kind, "metadata_only");
        assert.equal(doc.sections.length, 1);
        assert.equal(doc.sections[0].id, "metadata-only");
      }
    }
    payload.documents[0].source_kind = "pdf_text";
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(() => execFileSync(process.execPath, [
      "scripts/build-pagefind.mjs", "--input", input, "--output", output,
    ], { cwd: root, stdio: "pipe" }), (error) => {
      assert.match(error.stderr.toString(), /非結構化仿單來源/u);
      return true;
    });
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("rejects an unknown event type or non-TFDA event source", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "tfda-event-url-test-"));
  const input = path.join(temporaryRoot, "input.json");
  const output = path.join(temporaryRoot, "site");
  try {
    const payload = JSON.parse(
      await readFile(path.join(root, "tests/fixtures/pagefind-search-sample.json"), "utf8"),
    );
    payload.documents[1].official_events[0].event_type = "unknown_event";
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(
      () => execFileSync(process.execPath, [
        "scripts/build-pagefind.mjs", "--input", input, "--output", output,
      ], { cwd: root, stdio: "pipe" }),
      (error) => {
        assert.match(error.stderr.toString(), /未知的 TFDA 事件類型/u);
        return true;
      },
    );

    payload.documents[1].official_events[0].event_type = "safety_alert";
    payload.documents[1].official_events[0].source_url = "https://example.com/not-tfda.json";
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(
      () => execFileSync(process.execPath, [
        "scripts/build-pagefind.mjs", "--input", input, "--output", `${output}-second`,
      ], { cwd: root, stdio: "pipe" }),
      (error) => {
        assert.match(error.stderr.toString(), /不是 TFDA 開放資料 HTTPS 網址/u);
        return true;
      },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("accepts a real-size shortage status but keeps a hard length limit", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "tfda-event-length-test-"));
  const input = path.join(temporaryRoot, "input.json");
  const output = path.join(temporaryRoot, "site");
  try {
    const payload = JSON.parse(
      await readFile(path.join(root, "tests/fixtures/pagefind-search-sample.json"), "utf8"),
    );
    payload.documents[1].official_events[0].status = "供".repeat(917);
    await writeFile(input, JSON.stringify(payload), "utf8");
    execFileSync(process.execPath, [
      "scripts/build-pagefind.mjs", "--input", input, "--output", output,
    ], { cwd: root, stdio: "pipe" });

    payload.documents[1].official_events[0].status = "供".repeat(2001);
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(
      () => execFileSync(process.execPath, [
        "scripts/build-pagefind.mjs", "--input", input, "--output", `${output}-too-long`,
      ], { cwd: root, stdio: "pipe" }),
      (error) => {
        assert.match(error.stderr.toString(), /事件標題或狀態過長/u);
        return true;
      },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("rejects invalid dates or non-official links in NHI items", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "tfda-nhi-url-test-"));
  const input = path.join(temporaryRoot, "input.json");
  const output = path.join(temporaryRoot, "site");
  try {
    const payload = JSON.parse(
      await readFile(path.join(root, "tests/fixtures/pagefind-search-sample.json"), "utf8"),
    );
    payload.documents[0].nhi_items[0].effective_from = "2026-02-30";
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(
      () => execFileSync(process.execPath, [
        "scripts/build-pagefind.mjs", "--input", input, "--output", output,
      ], { cwd: root, stdio: "pipe" }),
      (error) => {
        assert.match(error.stderr.toString(), /健保有效日期格式錯誤/u);
        return true;
      },
    );

    payload.documents[0].nhi_items[0].effective_from = "2026-01-01";
    payload.documents[0].nhi_items[0].rule_url = "https://example.com/not-nhi";
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(
      () => execFileSync(process.execPath, [
        "scripts/build-pagefind.mjs", "--input", input, "--output", `${output}-second`,
      ], { cwd: root, stdio: "pipe" }),
      (error) => {
        assert.match(error.stderr.toString(), /不是指定的官方 HTTPS 網址/u);
        return true;
      },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});
