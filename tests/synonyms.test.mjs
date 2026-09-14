import assert from "node:assert/strict";
import test from "node:test";

import { validatedSynonyms } from "../scripts/validate-synonyms.mjs";

test("only reviewed synonym groups are published with audit fields", () => {
  const output = validatedSynonyms({
    schema_version: 1,
    entries: [
      {
        terms: [" 孕期 ", "懷孕"],
        reviewed: true,
        reviewer: "測試藥師",
        reviewed_at: "2026-09-15",
        note: "自動測試，不是正式醫療詞表。",
      },
      { terms: ["草稿甲", "草稿乙"], reviewed: false },
    ],
  }, "測試設定");
  assert.deepEqual(output, {
    schema_version: 1,
    entries: [{
      terms: ["孕期", "懷孕"],
      reviewed: true,
      reviewer: "測試藥師",
      reviewed_at: "2026-09-15",
      note: "自動測試，不是正式醫療詞表。",
    }],
  });
});

test("reviewed synonym groups require reviewer and a real calendar date", () => {
  const base = { schema_version: 1, entries: [{ terms: ["孕期", "懷孕"], reviewed: true }] };
  assert.throws(() => validatedSynonyms(base, "測試設定"), /審查人/u);
  assert.throws(
    () => validatedSynonyms({
      ...base,
      entries: [{ ...base.entries[0], reviewer: "測試藥師", reviewed_at: "2026-02-30" }],
    }, "測試設定"),
    /reviewed_at/u,
  );
});

test("ambiguous, duplicate or one-character synonym terms are rejected", () => {
  assert.throws(
    () => validatedSynonyms({
      schema_version: 1,
      entries: [
        { terms: ["孕期", "懷孕"], reviewed: true, reviewer: "甲藥師", reviewed_at: "2026-09-15" },
        { terms: ["孕期", "妊娠"], reviewed: true, reviewer: "乙藥師", reviewed_at: "2026-09-15" },
      ],
    }, "測試設定"),
    /已出現在/u,
  );
  assert.throws(
    () => validatedSynonyms({
      schema_version: 1,
      entries: [{ terms: ["噁", "噁心"], reviewed: false }],
    }, "測試設定"),
    /2 到 80/u,
  );
  assert.throws(
    () => validatedSynonyms({
      schema_version: 1,
      entries: [{ terms: ["renal impairment", "腎功能不全"], reviewed: false }],
    }, "測試設定"),
    /空白或查詢分隔符號/u,
  );
  assert.throws(
    () => validatedSynonyms({
      schema_version: 1,
      entries: [{ terms: ["Ｎａｕｓｅａ", "nausea"], reviewed: false }],
    }, "測試設定"),
    /重複/u,
  );
});
