import { chromium } from "@playwright/test";
import process from "node:process";

function options(argv) {
  const result = { url: "", query: "" };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--url") result.url = argv[++index];
    else if (argv[index] === "--query") result.query = argv[++index];
    else throw new Error(`未知參數：${argv[index]}`);
  }
  if (!/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\//u.test(result.url)) {
    throw new Error("量測工具只允許本機 HTTP 網址");
  }
  if ([...result.query].length < 2) throw new Error("查詢詞至少需要兩個字元");
  return result;
}

function metricMap(response) {
  return Object.fromEntries(response.metrics.map((item) => [item.name, item.value]));
}

function mib(value) {
  return Math.round((value / 1024 / 1024) * 100) / 100;
}

async function main({ url, query }) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const client = await page.context().newCDPSession(page);
    await client.send("Performance.enable");
    await page.goto(url, { waitUntil: "networkidle" });
    const before = metricMap(await client.send("Performance.getMetrics"));
    await page.locator("#all-terms").fill(query);
    const startedAt = await page.evaluate(() => performance.now());
    await page.getByRole("button", { name: "搜尋仿單" }).click();
    await page.waitForFunction(() => !/搜尋中|正在載入/u.test(document.querySelector("#status").textContent));
    const endedAt = await page.evaluate(() => performance.now());
    const after = metricMap(await client.send("Performance.getMetrics"));
    const resources = await page.evaluate(() => performance.getEntriesByType("resource").reduce(
      (sum, item) => ({
        encoded: sum.encoded + (item.encodedBodySize || 0),
        decoded: sum.decoded + (item.decodedBodySize || 0),
        count: sum.count + 1,
      }),
      { encoded: 0, decoded: 0, count: 0 },
    ));
    process.stdout.write(`${JSON.stringify({
      url,
      viewport: "390x844",
      query,
      status: await page.locator("#status").textContent(),
      cards: await page.locator("#results article").count(),
      search_ms: Math.round(endedAt - startedAt),
      initial_js_heap_mib: mib(before.JSHeapUsedSize || 0),
      result_js_heap_mib: mib(after.JSHeapUsedSize || 0),
      js_heap_delta_mib: mib((after.JSHeapUsedSize || 0) - (before.JSHeapUsedSize || 0)),
      resource_count: resources.count,
      transferred_mib: mib(resources.encoded),
      decoded_mib: mib(resources.decoded),
    }, null, 2)}\n`);
  } finally {
    await browser.close();
  }
}

try {
  await main(options(process.argv.slice(2)));
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
}
