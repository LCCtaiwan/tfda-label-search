import { expect, test } from "@playwright/test";

async function search(page, { all = "", any = "", excluded = "" }) {
  await page.locator("#all-terms").fill(all);
  await page.locator("#any-terms").fill(any);
  await page.locator("#exclude-terms").fill(excluded);
  await page.getByRole("button", { name: "搜尋仿單" }).click();
  await expect(page.locator("#status")).not.toHaveText(/搜尋中|正在載入/u);
}

test.beforeEach(async ({ page, context }) => {
  // Every browser request stays local; external API/file calls fail the test.
  await context.route(/^https?:\/\//u, async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== "http://127.0.0.1:4173") {
      await route.abort();
      throw new Error(`離線測試禁止外部請求：${url.origin}`);
    }
    await route.fallback();
  });
  await page.clock.setFixedTime("2026-09-16T08:00:00+08:00");
  await page.goto("/");
});

test("任意短詞與 AND、OR、NOT 會回傳正確章節", async ({ page }) => {
  await search(page, { all: "噁心" });
  await expect(page.locator("#status")).toHaveText("找到 3 筆結果。");

  await search(page, { all: "Nausea" });
  await expect(page.locator("#status")).toHaveText("找到 1 筆結果。");

  await search(page, { all: "腎功能不全" });
  await expect(page.locator("#status")).toHaveText("已顯示 50 筆，尚有更多結果。");
  await expect(page.locator("#results article")).toHaveCount(50);
  await expect(page.locator("#results article").first()).toContainText("腎功能不全");

  await search(page, { all: "懷孕 噁心" });
  await expect(page.locator("#status")).toHaveText("找到 2 個命中章節，來自 1 份仿單。");
  await expect(page.locator("#results article")).toHaveCount(2);
  await expect(page.locator("#results article").nth(0)).toContainText("懷孕");
  await expect(page.locator("#results article").nth(1)).toContainText("噁心");

  await search(page, { all: "噁心", excluded: "腹瀉" });
  await expect(page.locator("#status")).toHaveText("找到 2 筆結果。");

  await search(page, { any: "腹瀉 噁心" });
  await expect(page.locator("#status")).toHaveText("找到 4 個命中章節，來自 3 份仿單。");
});

test("頁尾顯示可追溯的資料版本", async ({ page }) => {
  await expect(page.locator("#freshness-warning")).toBeHidden();
  await expect(page.locator("#data-version")).toContainText("資料版本：2026-09-15");
  await expect(page.locator("#data-version")).toContainText("114 份");
  await expect(page.locator("#data-version")).toContainText(/指紋 [a-f0-9]{12}/u);
  await expect(page.locator("#coverage-summary")).toHaveText(
    "逐步補齊中：已有結構化仿單 113／有效藥證 114（99.12%）｜最後更新：2026-09-15｜1 份尚無結構化仿單（連食藥署仿單頁）",
  );
  await expect(page.locator("footer")).toContainText("衛生福利部食品藥物管理署");
  await expect(page.locator("footer")).toContainText("衛生福利部中央健康保險署");
  await expect(page.getByRole("link", { name: "政府資料開放授權條款-第1版" }))
    .toHaveAttribute("href", "https://data.gov.tw/license");
  const release = await page.evaluate(async () => {
    const response = await fetch("./data/release.json");
    return response.json();
  });
  expect(release.release_id).toBe("e2e-fixture");
  expect(release.app_revision).toMatch(/^[a-f0-9]{40}$/u);
  expect(release.data_revision).toMatch(/^[a-f0-9]{40}$/u);
  expect(release.official_snapshot_id).toBe("e2e-snapshot");
  expect(release.data_retrieved_at).toBe("2026-09-15T00:00:00+08:00");
  expect(release.coverage).toMatchObject({
    active_licenses: 114,
    structured_licenses: 113,
    metadata_only_licenses: 1,
  });
});

test("網站上線後資料超過十四天會直接警告", async ({ page }) => {
  await page.clock.setFixedTime("2026-10-01T08:00:00+08:00");
  await page.reload();
  const warning = page.locator("#freshness-warning");
  await expect(warning).toBeVisible();
  await expect(warning).toHaveText(
    "注意：這個網站的官方資料已 16 天沒有更新。請先到官方來源核對，再用於工作。",
  );
  await expect(page.locator("#data-version")).toContainText("資料版本：2026-09-15");

  await page.route("**/data/manifest.json", async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    delete manifest.data_retrieved_at;
    manifest.built_at = "2026-10-01T00:00:00Z";
    await route.fulfill({ response, json: manifest });
  });
  await page.reload();
  await expect(warning).toHaveText(
    "注意：無法確認官方資料更新日期。請先到官方來源核對，再用於工作。",
  );
  await expect(page.locator("#data-version")).toContainText("資料版本：日期未提供");
});

test("reviewed 測試同義詞會生效且英文不分大小寫", async ({ page }) => {
  await search(page, { all: "孕期" });
  await expect(page.locator("#status")).toHaveText("已顯示 50 筆，尚有更多結果。");
  await expect(page.locator("#results article")).toHaveCount(50);

  await search(page, { all: "queasiness" });
  await expect(page.locator("#status")).toHaveText("找到 1 筆結果。");
  await expect(page.locator("#results article")).toContainText("Nausea");
});

test("沒有結構化文字時只提供食藥署仿單頁", async ({ page }) => {
  const license = "測試藥證字第000004號";
  await page.goto(`/?q=${encodeURIComponent(license)}`);
  await expect(page.locator("#results article")).toHaveCount(1);
  await expect(page.locator("#results article")).toContainText("尚無結構化電子仿單文字");
  await expect(page.getByRole("link", { name: "食藥署仿單頁", exact: true }))
    .toHaveAttribute("href", `https://mcp.fda.gov.tw/im_detail_1/${encodeURIComponent(license)}`);
  await expect(page.locator("#results .resource-links a")).toHaveCount(1);
  await expect(page.getByRole("link", { name: /官方仿單檔案/u })).toHaveCount(0);
});

test("仿單頁備援拒絕指定路徑以外的網址並忽略舊檔案連結", async ({ page }) => {
  let unsafeUrl = "";
  await page.route("**/data/documents/*.json", async (route) => {
    const response = await route.fetch();
    const doc = await response.json();
    doc.official_url = unsafeUrl;
    doc.pdf_urls = ["https://mcp.fda.gov.tw/test/000004.pdf"];
    await route.fulfill({ response, json: doc });
  });
  for (const url of [
    "https://mcp.fda.gov.tw/test/000004.pdf",
    "https://mcp.fda.gov.tw/im_detail_1/",
    "https://mcp.fda.gov.tw/im_detail_1/abc/extra",
    "https://mcp.fda.gov.tw/im_detail_1/abc?file=1",
    "https://mcp.fda.gov.tw/im_detail_1/abc#file",
    "https://mcp.fda.gov.tw.evil.example/im_detail_1/abc",
    "https://user@mcp.fda.gov.tw/im_detail_1/abc",
    "http://mcp.fda.gov.tw/im_detail_1/abc",
    "javascript:alert(1)",
  ]) {
    unsafeUrl = url;
    await page.goto(`/?q=${encodeURIComponent("測試藥證字第000004號")}`);
    await expect(page.locator("#results article")).toHaveCount(1);
    await expect(page.locator("#results .resource-links a")).toHaveCount(0);
  }
});

test("其他 TFDA 官方資料以歷史關聯呈現，不冒充目前狀態", async ({ page }) => {
  await search(page, { all: "乙測試膠囊" });
  const events = page.locator(".official-events");
  await expect(events).toHaveCount(1);
  await expect(events.locator("summary")).toHaveText("曾出現在 TFDA 其他官方資料（1 筆）");
  await events.locator("summary").click();
  await expect(events).toContainText("不代表目前仍在回收、警示、風險管理或短缺");
  await expect(events).toContainText("藥品安全警訊資料｜2026-09-01｜TEST INGREDIENT");
  await expect(events.getByRole("link", { name: "TFDA 資料集來源" })).toHaveAttribute(
    "href",
    "https://data.fda.gov.tw/data/opendata/export/53/json",
  );
});

test("健保詳細資料有日期與官方來源，不冒充目前給付狀態", async ({ page }) => {
  await search(page, { all: "A000000001" });
  await expect(page.locator("#results article")).toHaveCount(1);
  await expect(page.locator("#results article .metadata").last()).toHaveText(
    "健保碼：A000000001｜ATC：A01AA01",
  );
  const details = page.locator(".nhi-details");
  await expect(details.locator("summary")).toHaveText("查看健保資料（2 筆）");
  await details.locator("summary").click();
  await expect(details).toContainText("不代表目前仍給付、支付價仍相同或適用個別情況");
  await expect(details).toContainText("健保碼：A000000001");
  await expect(details).toContainText("規格：10 MG");
  await expect(details).toContainText("支付價：1.5");
  await expect(details).toContainText("有效期間：2026-01-01～未載明迄日");
  await expect(details.getByRole("link", { name: "官方藥品資料" })).toHaveCount(2);
  await expect(details.getByRole("link", { name: "官方藥品資料" }).first()).toHaveAttribute(
    "href",
    "https://lmspiq.fda.gov.tw/web/DRPIQ/DRPIQ1000Result?licId=01000001",
  );
  await expect(details.getByRole("link", { name: "健保給付規定" })).toHaveCount(2);
  await expect(details.getByRole("link", { name: "健保給付規定" }).first()).toHaveAttribute(
    "href",
    "https://info.nhi.gov.tw/rule",
  );
});

test("常見詞可分批載入第 51 到 100 筆", async ({ page }) => {
  await search(page, { all: "懷孕" });
  await expect(page.locator("#results article")).toHaveCount(50);
  await expect(page.getByRole("button", { name: "載入更多結果" })).toBeVisible();

  await page.getByRole("button", { name: "載入更多結果" }).click();
  await expect(page.locator("#results article")).toHaveCount(100);
  await expect(page.locator("#status")).toHaveText("已顯示 100 筆，尚有更多結果。");
});

test("手機寬度仍能搜尋單一藥品", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await search(page, { all: "容量測試字第000042號" });
  await expect(page.locator("#results article")).toHaveCount(1);
  await expect(page.locator(".drug-name")).toHaveText("容量測試藥品 000042");
  await expect(page.locator("#status")).toHaveText("找到 1 筆結果。");

  await search(page, { all: "容量測試藥品 000042" });
  await expect(page.locator("#results article")).toHaveCount(1);
  await expect(page.locator("#status")).toHaveText("找到 1 筆結果。");
});

test("網址可帶入查詢、分享 AND OR NOT，並拒絕過大的查詢", async ({ page }) => {
  await page.goto("/?q=測試藥證字第000001號");
  await expect(page.locator("#all-terms")).toHaveValue("測試藥證字第000001號");
  await expect(page.locator("#results article")).toHaveCount(1);
  await expect(page.locator("#status")).toHaveText("找到 1 筆結果。");

  await search(page, { all: "噁心", any: "懷孕 嘔吐", excluded: "腹瀉" });
  const shared = new URL(page.url());
  expect(shared.searchParams.get("q")).toBe("噁心");
  expect(shared.searchParams.get("any")).toBe("懷孕 嘔吐");
  expect(shared.searchParams.get("exclude")).toBe("腹瀉");
  expect(shared.searchParams.has("all")).toBe(false);
  expect(shared.searchParams.has("not")).toBe(false);

  await search(page, { all: "甲乙 丙丁 戊己 庚辛 壬癸 子丑 寅卯 辰巳 午未 申酉 戌亥" });
  await expect(page.locator("#status")).toHaveText("三個欄位合計最多 10 個關鍵字。");

  await search(page, { all: "測".repeat(81) });
  await expect(page.locator("#status")).toHaveText("每個關鍵字需要 2 到 80 個字元。");

  await page.goto("/?all=噁心&not=腹瀉");
  await expect(page.locator("#status")).toHaveText("找到 2 筆結果。");
  expect(new URL(page.url()).searchParams.get("q")).toBe("噁心");
  expect(new URL(page.url()).searchParams.get("exclude")).toBe("腹瀉");
});
