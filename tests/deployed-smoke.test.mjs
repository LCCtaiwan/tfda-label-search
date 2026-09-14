import assert from "node:assert/strict";
import test from "node:test";

import { assertReleaseIdentity, checkedTarget, parseArgs } from "../scripts/verify-deployed.mjs";


test("deployment smoke arguments require an exact target and release", () => {
  const options = parseArgs([
    "--url", "https://example.github.io/tfda-label-search",
    "--expected-release-id", "release-123",
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
  };
  assert.doesNotThrow(() => assertReleaseIdentity(identity, "expected"));
  assert.throws(() => assertReleaseIdentity(identity, "other"), /部署版本不符/u);
  assert.throws(
    () => assertReleaseIdentity({ ...identity, data_revision: "data-state" }, "expected"),
    /不是完整 Git SHA/u,
  );
});
