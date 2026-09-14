# TFDA仿單搜尋

這是一個獨立於 ChemoDrugStable 的臺灣官方藥品仿單搜尋專案。目標是讓藥師及其他醫療人員用任意中文或英文關鍵字、藥名、成分、藥證字號或健保碼，找到仿單命中章節、原文、版本、日期與官方來源。

本專案使用 TFDA 與健保署公開資料，但不是衛生福利部、食藥署或健保署製作的官方網站。搜尋命中只表示官方資料提到該文字，不代表因果、適用、禁用、藥品可互換或符合健保給付。

## 使用者

- 主要使用者：藥師及其他醫療人員。
- 管理者：專案負責人，以及未來接手的主管或單位人員。
- 不收集、處理或儲存病人資料。

## 預定架構

- GitHub Pages：公開查詢網站。
- GitHub Actions：定期取得及驗證官方資料。
- Pagefind：每份仿單建立一筆候選索引；命中後再由瀏覽器逐章精確比對。
- TFDA 結構化電子仿單 API：主要仿單文字來源。
- TFDA 與健保署官方開放資料：藥證、成分、ATC、健保及安全資訊。

Pagefind 已通過 1,000 與 5,000 份合成容量試驗；正式發布前仍需用長短不同的真實仿單驗證涵蓋率與搜尋品質。這之前不建立正式 Supabase 或 Cloudflare 資料庫。

結構化仿單更新分成兩段：先依有效藥證小批續傳建庫；完成後改用官方最多 10 日的日期窗補更新。日期游標只追到臺灣上一個完整日，正式發布時不得落後超過 14 天。

正式發布不只相信狀態檔的 `ready`。系統會重新解析九個官方 raw 檔，核對 snapshot 的來源網址、SHA-256 與筆數，並逐張確認 downloaded 仿單的分片檔與藥證內容完全對得上。

## 與 ChemoDrugStable 的關係

- `chemodrugstable-query` 繼續負責化療藥品調配、安定性與院內核對資料。
- 本專案負責全臺藥品仿單、健保及官方安全資訊。
- 兩個網站可用網址參數互相連結，但各自建置、更新及回滾。

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

開啟 `http://localhost:8000` 後，可以輸入任意至少兩個字元的中文或英文文字。AND 欄每個詞都必須同時出現在同一章；OR 欄符合任一詞即可；NOT 欄會排除含有該詞的章節。結果每次顯示 50 筆，可按「載入更多結果」繼續查看。

目前已完成第一個小型可操作版本。先閱讀：

- `SPEC.md`：已確認的成品範圍與成功條件。
- `PROGRESS.md`：目前停點與下一步。
- `docs/develog.md`：決策與驗證紀錄。

- `docs/migration-inventory.md`：從既有工作副本移植或重寫的範圍。
- `docs/static-releases.md`：資料如何驗證、產生新版本，以及失敗時如何保留舊版。
- `docs/official-sources.md`：官方 API 能做什麼、九組來源、授權與批次下載邊界。
- `docs/publication-rights.md`：官方開放資料、結構化仿單及第三方程式的公開使用依據與排除範圍。
- `docs/capacity-study.md`：1,000／5,000 份容量試驗、被淘汰的舊架構與瀏覽器結果。
- `docs/deployment.md`：`data-state`、GitHub Pages、主管核准與回滾步驟。
- `docs/supervisor-guide.md`：主管核准與部署後檢查小抄。
- `docs/completion-audit.md`：逐項區分已證明、尚未證明與必須取得的外部授權。

`tests/fixtures/pagefind-search-sample.json` 是明確標示的合成測試資料；`structured-real-sample.json` 是一份既有的 TFDA API 實際回應解析結果。兩者都只用於本機驗證，尚未代表全量涵蓋率。

小型不可變 release 的完整命令在 `docs/static-releases.md`。它會把藥證、成分、健保碼、ATC、安全資料、仿單章節與官方入口組成一個可直接開啟的靜態網站。

正式網站會提供 `data/release.json`，可查到實際發布的程式、資料 commit、官方 snapshot 與真實資料擷取時間。Pages 部署完成後，`scripts/verify-deployed.mjs` 會用手機尺寸開啟正式網址、逐字核對兩個核准 SHA，再以正式目錄中的一張完整藥證搜尋一次。

## 重要限制

- 正式資料只使用可追溯的官方來源。
- 結構化仿單缺少時，清楚標示 PDF／圖片備援，不假裝有可搜尋文字。
- 更新失敗時保留上一個已驗證版本。
- 未經另外明確授權，不推送、部署、建立付費資源或大量呼叫官方 API。
- 目前兩個正式 workflow 都只允許手動執行；TFDA 確認批次頻率前不加入排程。
