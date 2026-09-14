import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, stat } from "node:fs/promises";
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
    assert.equal(manifest.document_count, 3);
    assert.equal(manifest.section_count, 4);
    assert.equal(manifest.record_count, 3);

    const documents = await readdir(path.join(output, "data", "documents"));
    assert.equal(documents.length, 3);
    const catalog = JSON.parse(await readFile(path.join(output, "data", "catalog.json"), "utf8"));
    assert.equal(catalog.document_count, 3);
    assert.equal(catalog.documents.length, 3);
    assert.ok(catalog.documents.every((item) => item.record_id && item.document_path));
    assert.ok(catalog.documents.every((item) => item.meta.record_id === item.record_id));
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
