import assert from "node:assert/strict";
import test from "node:test";

import {
  assertCoverage,
  assertReleaseIdentity,
  checkedTarget,
  parseArgs,
} from "../scripts/verify-deployed.mjs";


test("deployment smoke arguments require an exact target and release", () => {
  const options = parseArgs([
    "--url", "https://example.github.io/tfda-label-search",
    "--expected-release-id", "release-123",
    "--expected-app-sha", "a".repeat(40),
    "--expected-data-sha", "b".repeat(40),
  ]);
  assert.equal(options.expectedReleaseId, "release-123");
  assert.equal(checkedTarget(options.url).href, "https://example.github.io/tfda-label-search/");
  assert.throws(() => checkedTarget("http://example.com"), /只允許 HTTPS/u);
});

test("deployment smoke rejects a different or untraceable release", () => {
  const identity = {
    schema_version: 1,
    release_id: "expected",
    app_revision: "a".repeat(40),
    data_revision: "b".repeat(40),
    official_snapshot_id: "snapshot-123",
    data_retrieved_at: "2026-09-15T00:00:00+08:00",
  };
  assert.doesNotThrow(() => assertReleaseIdentity(identity, "expected", "a".repeat(40), "b".repeat(40)));
  assert.throws(
    () => assertReleaseIdentity(identity, "other", "a".repeat(40), "b".repeat(40)),
    /部署版本不符/u,
  );
  assert.throws(
    () => assertReleaseIdentity(
      { ...identity, data_revision: "data-state" },
      "expected",
      "a".repeat(40),
      "b".repeat(40),
    ),
    /不是完整 Git SHA/u,
  );
  assert.throws(
    () => assertReleaseIdentity(identity, "expected", "c".repeat(40), "b".repeat(40)),
    /與本次核准版本不符/u,
  );
  assert.throws(
    () => assertReleaseIdentity(
      { ...identity, data_retrieved_at: "2026-09-15" },
      "expected",
      "a".repeat(40),
      "b".repeat(40),
    ),
    /資料擷取時間/u,
  );
});

test("deployment smoke requires catalog, public coverage and approved release to agree", () => {
  const coverage = {
    schema_version: 1,
    document_count: 4,
    searchable_text_documents: 3,
    metadata_only_documents: 1,
    metadata_only_with_official_files: 1,
    metadata_only_without_official_files: 0,
    documents_with_official_files: 2,
    official_file_links: 2,
  };
  const identityCoverage = {
    active_licenses: 4,
    structured_licenses: 3,
    metadata_only_licenses: 1,
    metadata_only_with_official_files: 1,
    metadata_only_without_official_files: 0,
  };
  const catalog = {
    schema_version: 1,
    document_count: 4,
    documents: Array.from({ length: 4 }, (_, index) => ({ record_id: String(index) })),
  };
  assert.doesNotThrow(() => assertCoverage(coverage, identityCoverage, catalog));
  assert.throws(
    () => assertCoverage({ ...coverage, document_count: 5 }, identityCoverage, catalog),
    /不一致/u,
  );
  assert.throws(
    () => assertCoverage(coverage, { ...identityCoverage, structured_licenses: 2 }, catalog),
    /核准 release 不一致/u,
  );
});
