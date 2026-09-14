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

  try {
    execFileSync(process.execPath, [
      "scripts/build-pagefind.mjs",
      "--input",
      "tests/fixtures/pagefind-search-sample.json",
      "--output",
      output,
    ], { cwd: root, stdio: "pipe" });

    const manifest = JSON.parse(await readFile(path.join(output, "data", "manifest.json"), "utf8"));
    assert.equal(manifest.document_count, 4);
    assert.equal(manifest.section_count, 5);
    assert.equal(manifest.record_count, 4);
    assert.match(manifest.built_at, /^\d{4}-\d{2}-\d{2}T/u);
    assert.equal(manifest.data_retrieved_at, "2026-09-15T00:00:00Z");
    assert.match(manifest.dataset_sha256, /^[a-f0-9]{64}$/u);
    assert.equal(manifest.source_inputs.length, 1);

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
    assert.deepEqual(fallbackDocument.pdf_urls, ["https://mcp.fda.gov.tw/test/000004.pdf"]);
    for (const filename of documents) {
      const payload = await readFile(path.join(output, "data", "documents", filename), "utf8");
      assert.doesNotMatch(payload, /<img\b/iu);
      assert.doesNotMatch(payload, /data:image\//iu);
    }

    assert.ok((await stat(path.join(output, "pagefind", "pagefind.js"))).isFile());
    assert.ok((await stat(path.join(output, ".tfda-label-search-generated"))).isFile());
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});

test("rejects a fallback file outside the TFDA HTTPS host", async () => {
  const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "tfda-pagefind-url-test-"));
  const input = path.join(temporaryRoot, "input.json");
  const output = path.join(temporaryRoot, "site");
  try {
    const payload = JSON.parse(
      await readFile(path.join(root, "tests/fixtures/pagefind-search-sample.json"), "utf8"),
    );
    payload.documents.at(-1).pdf_urls = ["https://example.com/not-official.pdf"];
    await writeFile(input, JSON.stringify(payload), "utf8");
    assert.throws(
      () => execFileSync(process.execPath, [
        "scripts/build-pagefind.mjs",
        "--input", input,
        "--output", output,
      ], { cwd: root, stdio: "pipe" }),
      (error) => {
        assert.match(error.stderr.toString(), /不是 TFDA HTTPS 網址/u);
        return true;
      },
    );
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});
