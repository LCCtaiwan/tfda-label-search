# TFDA仿單搜尋

這是一個獨立於 ChemoDrugStable 的臺灣官方藥品仿單搜尋專案。目標是讓藥師及其他醫療人員用任意中文或英文關鍵字、藥名、成分、藥證字號或健保碼，找到仿單命中章節、原文、版本、日期與官方來源。

本專案使用 TFDA 與健保署公開資料，但不是衛生福利部、食藥署或健保署製作的官方網站。搜尋命中只表示官方資料提到該文字，不代表因果、適用、禁用、藥品可互換或符合健保給付。

藥品若曾出現在回收、安全警示、風險管理或短缺資料，結果卡會另外折疊顯示這段歷史官方關聯。它不會混入仿單全文命中，也不代表目前仍處於該狀態；使用者必須點回 TFDA 資料集核對最新資料。

有成功連接的健保品項會顯示支付價、有效期間、規格、劑型、藥商、給付章節與官方連結。這些欄位同樣只代表網站資料版本當時的紀錄；空白迄日不等於永久有效，支付價也不能當成現在價格。

## 使用者

- 主要使用者：藥師及其他醫療人員。
- 管理者：專案負責人，以及未來接手的主管或單位人員。
- 不收集、處理或儲存病人資料。

## 預定架構

- GitHub Pages：公開查詢網站。
- GitHub Actions：定期取得及驗證官方資料。
- Pagefind：每份仿單建立一筆候選索引；命中後再由瀏覽器逐章精確比對。
- TFDA 結構化電子仿單 API（`GetDrugDoc`）：唯一仿單內容來源。
- TFDA 與健保署官方開放資料：藥證、成分、ATC、健保及安全資訊。

Pagefind 已通過 1,000 與 5,000 份合成容量試驗；正式發布前仍需用長短不同的真實仿單驗證涵蓋率與搜尋品質。這之前不建立正式 Supabase 或 Cloudflare 資料庫。

結構化仿單更新分成兩段：先依有效藥證小批續傳建庫；完成後改用官方最多 10 日的日期窗補更新。日期游標只追到臺灣上一個完整日；初次建庫未完成可先上線，一旦有游標就不得落後超過 14 天，建庫完成卻無游標時先補跑授權增量。

「每批 25 張」只限制初次逐藥證建庫。日期增量是一種不同查詢，一個 10 日窗回傳幾份由 TFDA 決定，可能超過 25 份；因此 workflow 另設預設關閉的增量授權勾選，手動沒有本輪明確授權就不呼叫日期 API；排程以 `TFDA_SCHEDULE_AUTHORIZED=true` 作獨立增量授權。

正式發布不只相信狀態檔的 `ready`。系統會重新解析九個官方 raw 檔，核對 snapshot 的來源網址、SHA-256 與筆數，並逐張確認 downloaded 仿單的分片檔與藥證內容完全對得上。

九來源 snapshot 與已建立的結構化仿單增量在發布時各自都有 14 天門檻；任何一個過期都不能建立可部署候選版。網站上線後仍會每天重新計算並提示資料年齡。

第一次資料建立會下載九個批次來源，之後逐批補仿單時預設沿用同一份已驗證 snapshot，不會每 25 張就重抓九個大型檔案。每次手動資料工作仍要勾選本輪 API 授權；沿用的 snapshot 也會在任何仿單 API 呼叫前重新驗證。

沿用 snapshot 時會同時檢查年齡。超過 14 天就會在零次仿單 API 請求時停止，手動時管理者必須改選 `refresh_all_nine`；排程則會在缺少或超過 14 天時自動重抓全部九來源；不會先打完 25 次才等部署階段發現資料太舊。

## 與 ChemoDrugStable 的關係

- `chemodrugstable-query` 繼續負責化療藥品調配、安定性與院內核對資料。
- 本專案負責全臺藥品仿單、健保及官方安全資訊。
- 兩個網站可用網址參數互相連結，但各自建置、更新及回滾。

新網站接受 `q`（AND）、`any`（OR）與 `exclude`（NOT）網址參數，載入後會自動搜尋；完整格式與 ChemoDrugStable 串接邊界見 `docs/integration.md`。正式網址確定前不修改既有 ChemoDrugStable。

## 本機執行

需求：Python 3、Node.js 20 以上。

```sh
npm install --cache .npm-cache
npm test
npm run prepare:e2e
npm run test:e2e
npm run build -- \
  --input tests/fixtures/pagefind-search-sample.json \
  --input tests/fixtures/structured-real-sample.json \
  --output site
npm run serve
```

第一次在本機跑端到端測試前，需先執行 `npx playwright install chromium`。GitHub CI 會自動安裝瀏覽器。

開啟 `http://localhost:8000` 後，可以輸入任意 2–80 個字元的中文或英文文字，三欄合計最多 10 個詞。AND 欄每個詞都必須同時出現在同一章；OR 欄符合任一詞即可；NOT 欄會排除含有該詞的章節。結果每次顯示 50 筆，可按「載入更多結果」繼續查看；搜尋後可直接複製網址分享。

目前已完成第一個小型可操作版本。先閱讀：

- `SPEC.md`：已確認的成品範圍與成功條件。
- `PROGRESS.md`：目前停點與下一步。
- `docs/develog.md`：決策與驗證紀錄。

- `docs/migration-inventory.md`：從既有工作副本移植或重寫的範圍。
- `docs/static-releases.md`：資料如何驗證、產生新版本，以及失敗時如何保留舊版。
- `docs/official-sources.md`：官方 API 能做什麼、九組來源、授權與批次下載邊界。
- `docs/publication-rights.md`：官方開放資料、結構化仿單及第三方程式的公開使用依據與排除範圍。
- `docs/capacity-study.md`：1,000／5,000 份容量試驗、被淘汰的舊架構與瀏覽器結果。
- `docs/synonyms.md`：人工同義詞的草稿、藥師審查、衝突檢查與發布方式。
- `docs/integration.md`：`q`／`any`／`exclude` 深連結及與 ChemoDrugStable 的隔離串接方式。
- `docs/deployment.md`：`data-state`、GitHub Pages、主管核准與回滾步驟。
- `docs/supervisor-guide.md`：主管核准與部署後檢查小抄。
- `docs/completion-audit.md`：逐項區分已證明、尚未證明與必須取得的外部授權。
- `docs/official-file-probe.md`：保留的歷史抽查工具；目前發布流程不使用。

`tests/fixtures/pagefind-search-sample.json` 是明確標示的合成測試資料；`structured-real-sample.json` 是一份既有的 TFDA API 實際回應解析結果。兩者都只用於本機驗證，尚未代表全量涵蓋率。

小型不可變 release 的完整命令在 `docs/static-releases.md`。它會把藥證、成分、健保碼、ATC、安全資料、仿單章節與官方入口組成一個可直接開啟的靜態網站。

正式網站會提供 `data/release.json`，可查到實際發布的程式、資料 commit、官方 snapshot 與真實資料擷取時間。Pages 部署完成後，`scripts/verify-deployed.mjs` 會用手機尺寸開啟正式網址、逐字核對兩個核准 SHA，再以正式目錄中的一張完整藥證搜尋一次。

網站也會提供 `data/coverage.json`，涵蓋分類只有「有結構化仿單文字」與「尚無結構化仿單（連食藥署仿單頁）」。沒有結構化文字時仍可用藥名、藥證、成分或健保碼找到資料卡，但不能當成全文命中。

網站每次開啟都會用臺灣日期重新計算資料年齡。官方資料超過 14 天、日期缺少或日期晚於今天時，頁面頂端會直接警告；不會拿較新的網站建置日期假裝官方資料也有更新。

## 重要限制

- 正式資料只使用可追溯的官方來源。
- 仿單內容只使用 `GetDrugDoc` 結構化文字，不使用 PDF／圖片作內容或備援。
- 尚無結構化文字時只顯示「食藥署仿單頁」，網址為 `https://mcp.fda.gov.tw/im_detail_1/<URL 編碼的許可證字號>`；不保證該頁有仿單。發布與搜尋資料不含 `pdf_urls` 或官方仿單檔案連結。
- 更新失敗時保留上一個已驗證版本。
- 未經另外明確授權，不推送、部署、建立付費資源或大量呼叫官方 API。
- 日更及自動發布的授權、隱私與核准設定見下節；本機修改不等於已啟動 GitHub 工作。

## 每日補齊與首次核准（C-029）

不再要求 98% 涵蓋率才上線；完整性、來源、SHA／筆數、14 天新鮮度、無 PDF／只連指定食藥署仿單頁等關卡保留。網站顯示「逐步補齊中：已有結構化仿單 X／有效藥證 Y（Z%）」與最後更新日；`coverage.json` 保留。

Claude 須在 repository 設 Variables：`TFDA_API_CALLS_AUTHORIZED=true`、`TFDA_SCHEDULE_AUTHORIZED=true`（初次五張試跑先設 false）、`SUPERVISOR_APPROVAL_CONFIGURED=true`、`PUBLICATION_AUTHORIZED=true`；可選 Secret `FORMULARY_CSV_URL`（HTTPS UTF-8 CSV，含 `藥名,ATC碼,狀態`，停用列忽略）。院內清單只在記憶體排順序，不寫資料、附件、release 或 log，只記層級合計；未設或失敗照原順序。

Pages Source 選 GitHub Actions。`github-pages` environment 的 Required reviewers 加使用者本人 `LCCtaiwan`，Prevent self-review 不勾選；`github-pages-auto` environment 不設 reviewer／wait timer，允許預設分支。完整精確步驟見 [部署手冊](docs/deployment.md)。

首次手動 refresh 選 5 張、`refresh_all_nine`、一窗，勾 API 授權但不勾增量授權；確認後可先發網站。手動執行 Pages（app_ref=main、data_ref=data-state），檢查摘要後由本人在 GitHub 按 Review deployments → github-pages → Approve and deploy。核准部署與 smoke 成功後，才由工作在 `data-state/approved-app.json` 留下 app SHA／run 證據。

每日臺灣 10:23（cron `23 2 * * *`）需兩個 TFDA variable 同為 true，固定 500 張初次查詢或一個增量窗、2 秒間隔；snapshot 缺少或超過 14 天自動重抓。只有成功排程、同一已核准 app SHA、全部檢查通過才自動發布；首次、程式 SHA 改變與手動發布仍需 reviewer。停排程設 `TFDA_SCHEDULE_AUTHORIZED=false`；停發布設 `PUBLICATION_AUTHORIZED=false`。
