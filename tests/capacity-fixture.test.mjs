import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("capacity fixture is explicit, bounded and uniquely addressable", async () => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "tfda-capacity-test-"));
  const output = path.join(temporary, "fixture.json");
  try {
    execFileSync(process.execPath, [
      "scripts/generate-capacity-fixture.mjs",
      "--source", "tests/fixtures/structured-real-sample.json",
      "--documents", "3",
      "--output", output,
    ], { cwd: root });
    const payload = JSON.parse(await readFile(output, "utf8"));
    assert.equal(payload.document_count, 3);
    assert.match(payload.source.warning, /Not representative/u);
    assert.equal(new Set(payload.documents.map((item) => item.license_no)).size, 3);
    assert.ok(payload.documents.every((item) => item.source_kind === "synthetic_capacity_fixture"));
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
});
