# 開發紀錄

## Current Goal

建立獨立、可正式上線且可交接的「TFDA仿單搜尋」成品。第一個可驗證功能成果是 Pagefind 小型概念驗證：以真實結構化仿單章節證明繁體中文短詞、英文、結果原文及來源資訊可以在 GitHub Pages 架構中正確運作。

## Stack And Run Commands

預定技術：

- 靜態前端：HTML、CSS、JavaScript。
- 資料更新：Python 3、GitHub Actions。
- 全文搜尋：Pagefind。
- 發布：GitHub Pages。

實際使用命令：

```sh
npm install --cache .npm-cache
npm test
npm run build -- \
  --input tests/fixtures/pagefind-search-sample.json \
  --input tests/fixtures/structured-real-sample.json \
  --output site
npm run serve
```

## Decisions

- TFDA 仿單、全臺健保及安全資訊已超出化療調配專案範圍，因此建立獨立專案。
- 健保資料仍與藥證及仿單密切相關，保留為本專案的輔助資料，不再拆成第三個網站。
- `chemodrugstable-query` 保持不變；新網站日後以網址參數接收藥名、藥證或健保碼。
- Pagefind 是第一個正式候選搜尋層，必須以真實資料驗證，不能只依官方說明認定可行。
- 結構化電子仿單為主要文字來源；PDF 或圖片只作可追溯備援。
- 任意關鍵字搜尋至少支援中文二字詞；規格中的三個詞只是驗收樣本。
- 原作者已表示同意使用 `TFDA-drug-info-search`，但正式移植前仍應保存同意範圍及署名方式。
- 未經另外明確授權，不推送、部署、建立付費資源或大量呼叫官方 API。

## Completed Work

### 2026-09-15：專案規格確認

- 確認專案名稱、使用者、輸入、輸出、第一版範圍、不納入項目與成功證據。
- 確認新專案位置為 `/Users/lcc/Desktop/PGY許願池/tfda-label-search`。
- 建立 `SPEC.md`，並補充「噁心、懷孕、腎功能不全」只是驗收範例。
- 建立專案文件骨架；功能程式尚未開始移植。

### 2026-09-15：C-002 小型 Pagefind 概念驗證

- 完成來源檔案盤點，先移植結構化仿單解析與官方來源驗證；未帶入 Supabase／PGroonga。
- Pagefind 以「一個仿單章節一筆記錄」建索引。第一次瀏覽器測試發現同一藥品的章節共用官方網址時會被合併，已改成每章使用唯一索引網址，官方網址另以受控 metadata 保存。
- 索引輸出只包含清理後純文字，不保存內嵌圖片或 Base64 內容。
- 同義詞檔目前為空；只有人工審查並標示 `reviewed: true` 的詞組才會生效。

### 2026-09-15：C-003 靜態 release 與健保連接

- 以有效藥證清單作分母，將九組官方來源快照與結構化仿單整理成不可變 release。
- 健保碼只在官方健保品項 URL 的 `licId` 能唯一對上有效藥證時自動連接；缺少、找不到或多重對應都不猜測。
- 尚無結構化文字的有效藥證仍可由藥名、成分或健保碼找到，但清楚標示為 metadata-only。
- 第一次健保碼畫面測試發現 metadata 放在每個章節會產生 50 筆同藥結果，已拆成每藥一筆 metadata record，章節索引只保存章節文字。
- `active.json` 只在候選 release 完成所有驗證後原子切換；測試確認涵蓋率失敗不改動舊指標。

### 2026-09-15：C-004 官方來源與續傳更新

- 讀取並目視核對 TFDA 2025 年 9 月「藥品電子仿單交換格式」服務位址、參數、10 日日期上限與 XML 欄位表。
- 官方文件沒有寫出請求速率，因此程式採每 2 秒一次、每批 100 張的保守預設，但不把這個預設宣稱為官方允許值。
- 初次建庫按有效藥證逐筆續傳；查無結構化文件不是錯誤，但 30 日後會重查。
- 日後更新改用 10 日日期視窗；失敗會保存錯誤與原游標，下次從相同視窗重試。
- 九個官方批次檔必須一起成功才切換 snapshot，避免新舊來源混用。

### 2026-09-15：C-005 容量優化與分批結果

- 第一輪以每章一筆 Pagefind 記錄測 1,000 份、50,000 章，網站達 217 MB、52,242 個檔案、建置 78.83 秒，因此判定不通過。
- 改成每份仿單一筆候選索引；瀏覽器只載入候選文件 JSON，再用原文逐章執行 AND、OR、NOT 與人工審查同義詞比對。這個決定取代 C-002 的每章索引設計。
- 1,000 份壓縮後為 21 MB、5.84 秒；5,000 份為 100 MB、29.24 秒。
- 5,000 份本機 Chromium 第一次常見詞查詢 864 ms、重複查詢 191 ms、單一藥品 724 ms；主控台沒有錯誤或警告。
- 結果每次載入 50 筆；瀏覽器測試確認可由 50 筆增加至 100 筆。
- 容量資料是從一份真實結構樣本複製的合成資料，只能證明容量與基本速度，不能證明全臺涵蓋率或真實搜尋品質。

### 2026-09-15：C-006 真實瀏覽器 CI 與精確藥品目錄

- CI 新增 Playwright Chromium，使用 110 份合成容量資料加 3 份查詢樣本，自動測任意短詞、AND／OR／NOT、測試專用 reviewed 同義詞、50→100 筆、完整藥證、去重及手機寬度。
- 第一輪測試沒有把資料量造到 100 筆，屬於測試預期錯誤；修正後又發現完整合成藥證會被 Pagefind 中文切詞漏掉，這是實際功能錯誤。
- 建置時新增 `data/catalog.json`，先對藥名、藥證、成分與健保碼做正規化後的字面精確比對，再與 Pagefind 全文候選合併。
- 第二輪發現目錄與 Pagefind 同時命中時會顯示兩張卡；統一 `record_id` 後，自動與 5,000 份瀏覽器測試都只顯示一張。
- 加入目錄後的最終 5,000 份網站為 103 MB、建置 36.14 秒；第一次常見詞 1,115 ms、重複查詢 282 ms、單一藥品 1,023 ms。

### 2026-09-15：C-007 GitHub 免費資料續傳與主管核准

- 核對 GitHub 官方限制：Pages 站點 1 GB 限制下，103 MB 測試網站仍有空間；Actions cache 預設可能在 7 日未使用後移除，不可當權威資料；environment required reviewer 可在公開 repository 的免費方案使用。
- 依使用者要求請 Claude Code 獨立審查。它否決 draft release 作為唯一 head，建議用 `data-state` Git 分支的 commit 作原子指標；這與本專案的失敗保留舊版要求一致，因此採用。
- `refresh-data.yml` 只手動執行，每次下載九來源並查最多 25／50／100 張；整批失敗不 commit，成功才 push `data-state`，且同一時間只允許一輪。
- `deploy-pages.yml` 與下載完全分離；重新驗證資料、跑 30 個 Python／Node 與 4 個 Chromium 測試、通過 98% 結構化文字門檻後才產生 Pages artifact。
- 部署預設上鎖：`SUPERVISOR_APPROVAL_CONFIGURED` 未設為 `true` 時明確失敗；設為 true 前必須先在 `github-pages` environment 建立主管 required reviewer。
- 結構化文件改按證別前兩碼分片，避免 `data-state` 單一資料夾超過建議寬度。API 暫時錯誤支援最長 60 秒 `Retry-After`，仍失敗就保留舊 commit。

### 2026-09-15：C-008 離線發布演練與完成度稽核

- 新整合測試用九個官方格式 fixture 建 snapshot，依兩張藥證取得結構化 XML，產生完整 `data-state` manifest，再以 100% fixture 門檻建立 Pages 候選版；確認候選版不會自行建立 active 指標。
- 英文 `Nausea` 已納入 Chromium 測試；網站頁尾會顯示資料日期、份數與由輸入 SHA-256 組成的 12 碼指紋。
- 新增 localhost-only Playwright/CDP 量測工具。5,000 份、390×844 下，常見詞 536 ms、JS heap 增加 8.38 MiB、傳輸 4.33 MiB；完整藥證 221 ms、增加 6.61 MiB、傳輸 3.62 MiB。
- 建立 `docs/completion-audit.md`，逐項確認 Goal；真實代表性仿單、遠端 environment、正式小批、授權文字及正式回滾仍不得視為完成。

### 2026-09-15：C-009 資料分支容量保護

- 逐一對九個官方來源做 HTTP 標頭檢查，沒有下載檔案本文。來源皆可回應，但沒有提供可據以證明檔案大小的 `Content-Length`；健保端點不接受 HEAD，這些結果不能代替正式小批。
- `refresh-data.yml` 只把 `raw/` 與 snapshot manifest 移入 `data-state`，normalized 只存在於當次 runner，可由 raw 重建。
- `state_manifest.py` 會重建有效藥證清單，再檢查所有預備提交檔案；任何單檔超過內部 95 MiB 緩衝線就失敗，舊 commit 不受影響。
- manifest 額外記錄 `file_count`、`total_bytes`、`largest_file` 與 `largest_file_bytes`，供主管判斷容量是否持續成長。
- 離線整合測試已改成 raw-only 狀態，另以縮小測試門檻確認超大檔案會被拒絕；32 個 Python／Node 測試與三份 workflow YAML 通過。

### 2026-09-15：C-010 公開發布依據與雙重授權鎖

- 核對政府資料開放授權條款、TFDA 全部藥品許可證資料集、TFDA 網站資料開放宣告、健保用藥品項資料集與 `liangRXdev/TFDA-drug-info-search` 正式來源。
- 建立 `docs/publication-rights.md` 與 `config/publication-policy.json`：純文字可發布，內嵌圖片、PDF 鏡像、機關標誌與另有特別聲明素材排除。
- 目前沒有複製第三方程式；未來若改為 `consent_verified`，檢查器會要求同意紀錄、必要署名及實際檔案清單。
- 網站頁尾補齊 TFDA、健保署、資料名稱／版本與政府資料開放授權連結，Chromium 直接驗證使用者看得到。
- `release_preflight.py` 產生含政策與首頁 SHA-256 的 7 項稽核報告；授權核對超過一年或其他檢查缺一，就不產生可部署結果。
- 資料 workflow 新增 `TFDA_API_CALLS_AUTHORIZED` 鎖；部署 workflow 另需 `PUBLICATION_AUTHORIZED` 與既有主管 reviewer 鎖。
- 當時 39 個 Python、2 個 Node、5 個 Chromium 測試與三份 workflow YAML 通過。

### 2026-09-15：C-011 可追溯部署、正式網址 smoke 與回滾入口

- 靜態 release 在封存前寫入 `site/data/release.json`，包含 release ID、程式完整 SHA、資料完整 SHA、來源雜湊與涵蓋率；正式 release 缺少兩個 40 碼 SHA 會失敗。
- Pages workflow 新增 `app_ref`、`data_ref`；一般發布使用 branch，回滾填入上一個正常版本的完整 SHA，兩者都先解析並保存為不可變 commit。
- 新增 `verify-deployed.mjs`。部署後用 390×844 Chromium 開正式網址、核對 release ID 與兩個 SHA，從 catalog 選一張完整藥證搜尋，並要求主控台 0 錯誤。
- 本機 smoke 演練通過：`e2e-fixture`、查詢「測試藥證字第000001號」、1 筆結果、console 0、1.653 秒。
- 目前總計 40 個 Python、4 個 Node 與 5 個 Chromium 測試通過；三份 workflow YAML 可解析。

### 2026-09-15：C-012 初次建庫後的正式增量更新

- 稽核發現 `fetch_updates.py` 雖已存在，但 `refresh-data.yml` 只呼叫逐藥證建庫，完成後不會更新已下載的仿單；新增 `sync_structured.py` 並接入 workflow。
- `state.json` 新增 `initial_started_on`。最後一批初次資料先獨立 commit，下一輪才從建庫開始日以最多 10 日一窗補更新，避免兩種 API 請求無間隔相接。
- 日期游標只追到臺灣上一個完整日，避免白天先把今日標成完成；失敗保留原游標，更新狀態與文件都留在未 push 的 runner，遠端仍是上一個完整 commit。
- 增量模式不讓舊 `no_document` 的逐張重查阻塞日期窗；新藥證仍優先逐張補抓，日期回應有新文件時會把 `no_document` 提升為 `downloaded`。
- 舊日期回補會合併既有文件，只保留日期／版本較新的內容；新增自然版本排序測試，確認版本 10 大於版本 9。
- `data-state-manifest.json` 新增增量初始化、下一日期、落後天數及最後完成日；正式 Pages 建置要求游標存在且落後不超過 14 天。
- 目前總計 49 個 Python、4 個 Node 與 5 個 Chromium 測試通過；三份 workflow YAML 可解析。

### 2026-09-15：C-013 正式資料完整性與部署身分核對

- 完成 production-readiness 稽核，發現 data-state manifest 原本只重建 licenses，其他八個 raw 沒有在部署前與 snapshot 重新比對；改為九個來源全部重解析，逐一核對官方網址、SHA-256、原始筆數與整理筆數。
- 原本只用檔案總數判斷 downloaded 仿單是否齊全；改為逐一核對狀態中的藥證代碼、分片路徑、JSON 格式與內容藥證，並拒絕沒有對應 downloaded 狀態的額外 JSON。
- 靜態 release 新增 `official_snapshot_id` 與 `data_retrieved_at`；Pagefind 頁尾資料日期改用 snapshot 真正擷取時間，不再用部署建置時間。
- 部署 smoke 新增完整 app/data SHA 輸入與逐字比對；回滾時 checkout 被發布的 app SHA 執行檢查，避免用新版檢查器驗舊版網站。
- 依 GitHub 官方 repository release API 在 2026-09-15 核對 action 版本；三份 workflow 的官方 Actions 全部固定到完整 commit SHA，另有回歸測試禁止回到浮動 tag。
- 將規格指定的「腎功能不全」加入 Chromium 自動驗收；容量 fixture 會命中超過 50 筆，測試確認分批狀態與命中原文。
- 本機更新後 smoke 通過：`e2e-fixture`、app/data SHA 完全相符、完整藥證 1 筆、390×844、console 0、1.000 秒。
- `npm audit --audit-level=high --package-lock-only` 回報 0 個已知漏洞。
- 目前總計 54 個 Python、4 個 Node 與 5 個 Chromium 測試通過；三份 workflow YAML 可解析。

### 2026-09-15：C-014 小批建庫流量與逐次授權保護

- 稽核發現 `refresh-data.yml` 雖然文件要求第一次 25 張，畫面預設卻是 100 張；已將預設改為 25，保留 50／100 但必須由負責人另外決定。
- 原流程每次補一小批結構化仿單都重新下載九個批次來源；若以 25 張建立大量藥證會造成大量重複下載。新增 `official_source_mode`，平常預設 `reuse_existing`，第一次或確實要更新批次資料才用 `refresh_all_nine`。
- 第一次沒有 `data-state` 卻選沿用時會立即失敗；已用暫存 Git 專案確認 `git switch --orphan` 會得到零追蹤檔與乾淨工作樹。
- 長期 repository variable 之外，新增每次 workflow 都必須勾選的 `authorization_ack`，避免一次授權被默認為永久同意所有後續 API 執行。
- 已核對 GitHub 官方 workflow 文件：`inputs` context 會保留 boolean 型別，因此以 `inputs.authorization_ack != true` 判斷勾選狀態。
- 新增 `validate_official_snapshot.py`；不論 snapshot 是沿用或剛下載，都在 `sync_structured.py` 前重新核對九來源。測試確認竄改健保 raw 時會在仿單 API 前停止。
- 目前總計 56 個 Python、4 個 Node 與 5 個 Chromium 測試通過；三份 workflow YAML 可解析。

### 2026-09-15：C-015 官方 PDF／圖片備援連結

- 規格稽核發現 `static_release.py` 已把 TFDA 清冊的 `pdf_urls` 加到文件，但 `build-pagefind.mjs` 沒有複製該欄位，前端也沒有顯示，因此原先「有 PDF 備援」只存在中間資料、使用者實際看不到。
- Pagefind 建置現在保存去重後的 `pdf_urls`，並只接受無帳密、標準 HTTPS 埠且主機為 `mcp.fda.gov.tw` 的網址；非 TFDA 網域會讓建置失敗。
- 結果卡加入官方仿單檔案連結，仍保留官方電子仿單入口；只連回官方站，不下載、嵌入或公開鏡像 PDF／圖片。
- 測試 fixture 新增一張 metadata-only 藥品。Chromium 以藥名找到唯一結果，確認顯示「尚無結構化電子仿單文字」與正確官方檔案網址。
- Playwright CLI 技能的 wrapper 在取得套件時無輸出卡住約 50 秒，已中止且未做全域安裝；額外 CLI 截圖未執行。專案既有 `@playwright/test` Chromium 六項操作驗收已實際通過。
- 目前總計 56 個 Python、5 個 Node 與 6 個 Chromium 測試通過。

### 2026-09-15：C-016 公開資料涵蓋與缺件摘要

- 完成度稽核發現 release 原本只報告結構化涵蓋率；主管與網站使用者無法分辨 metadata-only 藥證有沒有官方備援檔案。
- Pagefind 建置新增 `site/data/coverage.json`，每張資料互斥分成有可搜尋文字、只有官方檔案連結、文字與檔案皆無；另記錄具有檔案的文件數與去重後連結總數。
- 前端同時讀取 manifest 與 coverage；schema、文件總數或三類加總不一致時顯示「無法讀取／請勿假設資料完整」，不展示看似正常的數字。
- release 稽核的 `coverage.json` 同步加入 metadata-only 有／無檔案、具有官方檔案的藥證數與連結總數，供主管核准時比較。
- 不依網址副檔名猜測 PDF 或圖片；正式小批取得實際檔案前，只能證明有通往 TFDA 的官方檔案連結。
- 正式部署 smoke 新增三方比對：公開 `coverage.json`、藥品目錄及核准 release 涵蓋數任一不一致就失敗。
- 本機完整 smoke 通過：114 份目錄、113 份可搜尋文字、1 份只有官方檔案、0 份兩者皆無；完整藥證搜尋 1 筆，390×844，console 0。
- 完整驗收通過：56 個 Python、6 個 Node、6 個 Chromium 與三份 workflow YAML。

## Verification Status

- 規格：使用者已確認。
- Python／Node：62 個測試通過（56 Python + 6 Node）。
- Node.js：Pagefind 建置與容量 fixture 測試共 2 個通過。
- 小型索引：4 份文件、54 個章節，整個靜態網站約 876 KB，其中 Pagefind 約 820 KB。
- 真實瀏覽器：`噁心` 3 筆、`懷孕` 2 筆、`腎功能不全` 2 筆；`懷孕 AND 噁心` 1 筆；`噁心 NOT 腹瀉` 2 筆；`腹瀉 OR 腎功能不全` 3 筆。
- 章節展開後會載入原文；桌機 1440×1000 與手機 390×844 版面通過目視檢查；主控台 0 錯誤。
- Release 瀏覽器驗證：健保碼 `A016162100` 只回 1 張正確藥品資料卡，並顯示成分、ATC、仿單版本及官方入口；主控台 0 錯誤。
- 合成容量驗證：1,000 份為 21 MB；最終 5,000 份為 103 MB；分批結果由 50 筆正確增加至 100 筆。
- 真實瀏覽器自動測試：6 個 Chromium 測試通過。
- 線上服務：未建立或修改。
- 既有 ChemoDrugStable：未修改。

## Recommended Next Step

由使用者決定新 GitHub repository 的擁有者、公開／私人設定與主管帳號；取得推送及第一次正式 25 張小批授權後，才建立遠端並驗證真實 workflow。TFDA 頻率確認前不增加批量或排程。
