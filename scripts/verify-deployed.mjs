#!/usr/bin/env node

import { mkdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";


export function parseArgs(argv) {
  const options = {
    url: "",
    expectedReleaseId: "",
    expectedAppSha: "",
    expectedDataSha: "",
    output: "",
    allowLocal: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--url") options.url = argv[++index] ?? "";
    else if (value === "--expected-release-id") options.expectedReleaseId = argv[++index] ?? "";
    else if (value === "--expected-app-sha") options.expectedAppSha = argv[++index] ?? "";
    else if (value === "--expected-data-sha") options.expectedDataSha = argv[++index] ?? "";
    else if (value === "--output") options.output = argv[++index] ?? "";
    else if (value === "--allow-local") options.allowLocal = true;
    else throw new Error(`未知參數：${value}`);
  }
  if (
    !options.url
    || !options.expectedReleaseId
    || !/^[a-f0-9]{40}$/u.test(options.expectedAppSha)
    || !/^[a-f0-9]{40}$/u.test(options.expectedDataSha)
  ) {
    throw new Error("必須提供網址、release ID 與兩個完整 Git SHA");
  }
  return options;
}

export function checkedTarget(rawUrl, allowLocal = false) {
  const target = new URL(rawUrl);
  const local = ["127.0.0.1", "localhost"].includes(target.hostname);
  if (target.username || target.password) throw new Error("網址不可包含帳號或密碼");
  if (target.protocol !== "https:" && !(allowLocal && local && target.protocol === "http:")) {
    throw new Error("正式 smoke test 只允許 HTTPS；本機測試須明確使用 --allow-local");
  }
  target.hash = "";
  if (!target.pathname.endsWith("/")) target.pathname += "/";
  return target;
}

export function assertReleaseIdentity(
  identity,
  expectedReleaseId,
  expectedAppSha,
  expectedDataSha,
) {
  if (!identity || identity.schema_version !== 1) throw new Error("release.json 格式錯誤");
  if (identity.release_id !== expectedReleaseId) {
    throw new Error(`部署版本不符：預期 ${expectedReleaseId}，實際 ${identity.release_id || "空白"}`);
  }
  for (const field of ["app_revision", "data_revision"]) {
    if (!/^[a-f0-9]{40}$/u.test(String(identity[field] ?? ""))) {
      throw new Error(`release.json 的 ${field} 不是完整 Git SHA`);
    }
  }
  if (identity.app_revision !== expectedAppSha || identity.data_revision !== expectedDataSha) {
    throw new Error("部署的程式或資料 SHA 與本次核准版本不符");
  }
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/u.test(String(identity.official_snapshot_id ?? ""))) {
    throw new Error("release.json 缺少可追溯的官方 snapshot ID");
  }
  const retrievedAt = String(identity.data_retrieved_at ?? "");
  if (!/(?:Z|[+-]\d{2}:\d{2})$/u.test(retrievedAt) || Number.isNaN(Date.parse(retrievedAt))) {
    throw new Error("release.json 缺少含時區的資料擷取時間");
  }
}

async function atomicJson(output, value) {
  if (!output) return;
  const target = path.resolve(output);
  await mkdir(path.dirname(target), { recursive: true });
  const temporary = `${target}.tmp-${process.pid}`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporary, target);
}

export async function verifyDeployment(options) {
  const started = Date.now();
  const target = checkedTarget(options.url, options.allowLocal);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  try {
    const response = await page.goto(target.href, { waitUntil: "networkidle", timeout: 30_000 });
    if (!response?.ok()) throw new Error(`首頁回應失敗：HTTP ${response?.status() ?? "unknown"}`);
    await page.locator("#search-form").waitFor();

    const payload = await page.evaluate(async () => {
      const load = async (relative) => {
        const response = await fetch(new URL(relative, document.baseURI));
        if (!response.ok) throw new Error(`${relative} HTTP ${response.status}`);
        return response.json();
      };
      return {
        identity: await load("data/release.json"),
        catalog: await load("data/catalog.json"),
        footer: document.querySelector("footer")?.textContent ?? "",
      };
    });
    assertReleaseIdentity(
      payload.identity,
      options.expectedReleaseId,
      options.expectedAppSha,
      options.expectedDataSha,
    );
    if (!payload.footer.includes("政府資料開放授權條款-第1版")) {
      throw new Error("正式網站頁尾缺少授權聲明");
    }
    const document = payload.catalog?.documents?.find((item) => item.license_no);
    if (!document) throw new Error("正式網站目錄沒有可用藥證");

    await page.locator("#all-terms").fill(document.license_no);
    await page.getByRole("button", { name: "搜尋仿單" }).click();
    await page.locator("#results article").first().waitFor({ timeout: 30_000 });
    const resultCount = await page.locator("#results article").count();
    if (resultCount < 1) throw new Error(`完整藥證搜尋沒有結果：${document.license_no}`);
    if (consoleErrors.length) throw new Error(`瀏覽器主控台錯誤：${consoleErrors.join("；")}`);

    const report = {
      schema_version: 1,
      verified_at: new Date().toISOString(),
      ready: true,
      url: target.href,
      release_id: payload.identity.release_id,
      app_revision: payload.identity.app_revision,
      data_revision: payload.identity.data_revision,
      official_snapshot_id: payload.identity.official_snapshot_id,
      data_retrieved_at: payload.identity.data_retrieved_at,
      query: document.license_no,
      result_count: resultCount,
      viewport: "390x844",
      console_errors: 0,
      duration_ms: Date.now() - started,
    };
    await atomicJson(options.output, report);
    return report;
  } finally {
    await browser.close();
  }
}

async function main() {
  const report = await verifyDeployment(parseArgs(process.argv.slice(2)));
  process.stdout.write(`${JSON.stringify(report)}\n`);
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
