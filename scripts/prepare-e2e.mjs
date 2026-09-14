import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = path.resolve(import.meta.dirname, "..");
const outputRoot = path.join(root, "output", "e2e");
const capacityFile = path.join(outputRoot, "capacity.json");
const site = path.join(outputRoot, "site");

execFileSync(process.execPath, [
  "scripts/generate-capacity-fixture.mjs",
  "--source", "tests/fixtures/structured-real-sample.json",
  "--output", capacityFile,
  "--documents", "110",
], { cwd: root, stdio: "inherit" });

execFileSync(process.execPath, [
  "scripts/build-pagefind.mjs",
  "--input", "tests/fixtures/pagefind-search-sample.json",
  "--input", capacityFile,
  "--output", site,
], { cwd: root, stdio: "inherit" });

await mkdir(path.join(site, "data"), { recursive: true });
await writeFile(path.join(site, "data", "synonyms.json"), `${JSON.stringify({
  schema_version: 1,
  entries: [{
    terms: ["孕期", "懷孕"],
    reviewed: true,
    reviewer: "automated-test-fixture",
    note: "只存在於自動測試輸出，不會寫入正式同義詞設定。",
  }],
}, null, 2)}\n`, "utf8");
await writeFile(path.join(site, "data", "release.json"), `${JSON.stringify({
  schema_version: 1,
  release_id: "e2e-fixture",
  created_at: new Date().toISOString(),
  app_revision: "a".repeat(40),
  data_revision: "b".repeat(40),
}, null, 2)}\n`, "utf8");
