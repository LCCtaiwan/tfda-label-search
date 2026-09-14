#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

function plain(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalized(value) {
  return plain(value).normalize("NFKC").toLocaleLowerCase("zh-TW");
}

function validCalendarDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

export function validatedSynonyms(payload, source = "同義詞設定") {
  if (payload?.schema_version !== 1 || !Array.isArray(payload.entries)) {
    throw new Error(`${source} 必須是 schema_version 1 且含 entries 清單`);
  }
  const reviewedTerms = new Map();
  const published = [];
  for (const [index, entry] of payload.entries.entries()) {
    const label = `${source} 第 ${index + 1} 組`;
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error(`${label} 必須是物件`);
    }
    if (typeof entry.reviewed !== "boolean") {
      throw new Error(`${label} 的 reviewed 必須明確為 true 或 false`);
    }
    if (!Array.isArray(entry.terms) || entry.terms.length < 2 || entry.terms.length > 20) {
      throw new Error(`${label} 必須有 2 到 20 個詞`);
    }
    const terms = entry.terms.map(plain);
    if (terms.some((term) => [...term].length < 2 || [...term].length > 80 || /[\s,，;；]/u.test(term))) {
      throw new Error(`${label} 的每個詞必須是 2 到 80 個字元，且不可包含空白或查詢分隔符號`);
    }
    const normalizedTerms = terms.map(normalized);
    if (new Set(normalizedTerms).size !== normalizedTerms.length) {
      throw new Error(`${label} 含有正規化後重複的詞`);
    }
    if (!entry.reviewed) continue;

    const reviewer = plain(entry.reviewer);
    const reviewedAt = plain(entry.reviewed_at);
    if (!reviewer || [...reviewer].length > 100 || /[\u0000-\u001f\u007f]/u.test(reviewer)) {
      throw new Error(`${label} 缺少 100 字元內的審查人或審查角色`);
    }
    if (!validCalendarDate(reviewedAt)) {
      throw new Error(`${label} 缺少有效的 reviewed_at（YYYY-MM-DD）`);
    }
    for (const [termIndex, term] of normalizedTerms.entries()) {
      const previous = reviewedTerms.get(term);
      if (previous !== undefined) {
        throw new Error(`${label} 的「${terms[termIndex]}」已出現在第 ${previous + 1} 組`);
      }
      reviewedTerms.set(term, index);
    }
    const safe = {
      terms,
      reviewed: true,
      reviewer,
      reviewed_at: reviewedAt,
    };
    const note = plain(entry.note);
    if ([...note].length > 500 || /[\u0000-\u001f\u007f]/u.test(note)) {
      throw new Error(`${label} 的 note 必須在 500 字元內且不可含控制字元`);
    }
    if (note) safe.note = note;
    published.push(safe);
  }
  return { schema_version: 1, entries: published };
}

export async function validateFile(filePath) {
  const source = path.resolve(filePath);
  let payload;
  try {
    payload = JSON.parse(await readFile(source, "utf8"));
  } catch (error) {
    throw new Error(`${source} 無法讀取或不是有效 JSON：${error.message}`);
  }
  return validatedSynonyms(payload, source);
}

async function main() {
  const filePath = process.argv[2] ?? "config/synonyms.json";
  if (process.argv.length > 3) throw new Error("用法：node scripts/validate-synonyms.mjs [檔案]");
  const result = await validateFile(filePath);
  process.stdout.write(`${JSON.stringify({
    source: path.resolve(filePath),
    reviewed_groups: result.entries.length,
    reviewed_terms: result.entries.reduce((sum, entry) => sum + entry.terms.length, 0),
  })}\n`);
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
