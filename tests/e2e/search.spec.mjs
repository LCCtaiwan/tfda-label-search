import { expect, test } from "@playwright/test";

async function search(page, { all = "", any = "", excluded = "" }) {
  await page.locator("#all-terms").fill(all);
  await page.locator("#any-terms").fill(any);
  await page.locator("#exclude-terms").fill(excluded);
  await page.getByRole("button", { name: "搜尋仿單" }).click();
  await expect(page.locator("#status")).not.toHaveText(/搜尋中|正在載入/u);
}

test.beforeEach(async ({ page }) => {
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
  await expect(page.locator("#status")).toHaveText("找到 1 筆結果。");

  await search(page, { all: "噁心", excluded: "腹瀉" });
  await expect(page.locator("#status")).toHaveText("找到 2 筆結果。");

  await search(page, { any: "腹瀉 噁心" });
  await expect(page.locator("#status")).toHaveText("找到 3 筆結果。");
});

test("頁尾顯示可追溯的資料版本", async ({ page }) => {
  await expect(page.locator("#data-version")).toContainText("資料版本：2026-09-15");
  await expect(page.locator("#data-version")).toContainText("113 份");
  await expect(page.locator("#data-version")).toContainText(/指紋 [a-f0-9]{12}/u);
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
});

test("只有 reviewed 的測試同義詞會生效", async ({ page }) => {
  await search(page, { all: "孕期" });
  await expect(page.locator("#status")).toHaveText("已顯示 50 筆，尚有更多結果。");
  await expect(page.locator("#results article")).toHaveCount(50);
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
