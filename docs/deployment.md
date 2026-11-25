# GitHub Pages 部署

## 更新與發布

`refresh-data.yml` 保存完整成功批次到 `data-state`；失敗不 push。`deploy-pages.yml` 讀取不可變的 app/data SHA，重驗來源、資料與網站後才發布。初次建庫未完成也可發布，不再要求 98% 結構化文字涵蓋率。網站顯示「逐步補齊中：已有結構化仿單 X／有效藥證 Y（Z%）」與官方資料最後更新日期，並保留 `coverage.json`。

資料完整性關卡仍包括九來源網址、SHA-256、原始／整理筆數、downloaded 仿單路徑及藥證一致、結構化文字來源、無 PDF／官方檔案備援連結、食藥署備援頁僅允許 `https://mcp.fda.gov.tw/im_detail_1/<編碼藥證>`、95 MiB 單檔保護、同義詞及發布權利／署名檢查。九來源 snapshot 必須不超過 14 天。初次建庫尚未完成且沒有增量游標時，允許先發布；一旦已有游標，就算有新增藥證尚未補完，也須通過游標格式、來源版本、無未解決錯誤及落後不超過 14 天。初次建庫完成卻沒有游標仍會停止，須再跑一次獲授權的增量更新。

GitHub Actions cache 不是權威資料。`data-state` 只保存官方 raw、續傳狀態、結構化仿單及核准紀錄，不重複保存 normalized 資料；超過 95 MiB 先停下評估儲存方式，不能繞過保護。失敗不會用空資料覆蓋上一個已驗證版本。

## Claude 一次性設定

1. 審查本次差異、重跑離線與 Chromium 測試，提交並把核准的程式／workflow 放到 repository 預設分支（通常 `main`）。排程與 `workflow_run` 需要 workflow 已在預設分支。這份文件不表示本機已替你操作 GitHub。
2. Settings → Pages → Source 選 **GitHub Actions**。Settings → Actions → General 確認工作可使用 `GITHUB_TOKEN` 寫入 `data-state`，且分支規則允許這兩個 workflow 的 bot 正常推送；不用 PAT。
3. Settings → Environments 建立 **`github-pages`**：Required reviewers 加入使用者本人的 GitHub 帳號（本案 `LCCtaiwan`）。使用者要核准自己發起的 run，因此 **Prevent self-review 不勾選**。有 reviewer 才能設下方的確認變數；不得用變數代替真正的環境保護。
4. 建立 **`github-pages-auto`** environment：**不設 Required reviewers、不設 wait timer**；部署分支規則允許預設分支。`github-pages` 也要允許實際發起人工發布的分支；一般統一從 `main` 執行。兩個 environment 都必須能發布 Pages。
5. Settings → Secrets and variables → Actions → **Variables** 設定以下 repository variables（不是 environment variables）：

| 變數 | 值與用途 |
|---|---|
| `TFDA_API_CALLS_AUTHORIZED` | `true` 才可下載；關閉設 `false` |
| `TFDA_SCHEDULE_AUTHORIZED` | 日更授權後設 `true`；初次五張試跑先設 `false` |
| `SUPERVISOR_APPROVAL_CONFIGURED` | 確認 `github-pages` reviewer 生效後才設 `true` |
| `PUBLICATION_AUTHORIZED` | 明確同意公開後設 `true`；`false` 會阻止人工與自動部署 |

6. 同頁 **Secrets** 可選設 **`FORMULARY_CSV_URL`**：能回傳 UTF-8 CSV 的 HTTPS 網址，包含 `藥名,ATC碼,狀態` 表頭，可有額外欄位。此網址只存 secret，不放 repository variable、程式或文件。沒有 secret、下載失敗、過大或格式錯誤會警告後照原順序，不停止官方更新。

院內 CSV 僅在下載程序記憶體中使用；`狀態=停用` 忽略。待處理藥證依「官方 ATC 完全相符＋英文藥名／成分完整 token 相符 → 僅 ATC 相符 → 其餘」排序，每層維持原順序。英文比對不分大小寫，排除 tablet 等通用劑型詞；名稱與 ATC 必須來自同一筆院內對應。官方 ATC／名稱來自已驗證 NHI、藥證與成分資料，不用院內清單修改公開內容。CSV、網址、藥名及比對明細不寫 repo、`data-state`、artifact、release 或 log；只輸出 `priority tier1: N` 等合計，網站不標示院內品項。

Required reviewer 的可用性取決於 repository 可見度與 GitHub 方案；若設定頁沒有這個功能，先解決環境保護，不可直接把確認變數設為 `true`。

## 初次試跑與首次發布

1. 先設 `TFDA_API_CALLS_AUTHORIZED=true`、`TFDA_SCHEDULE_AUTHORIZED=false`。Actions → **Refresh TFDA data state** → Run workflow（選已審查分支）：`max_items=5`、`official_source_mode=refresh_all_nine`、`max_update_windows=1`、`authorization_ack=true`、`incremental_authorization_ack=false`。
2. 查 run summary、來源預檢、`pending_licenses`、涵蓋數與 `data-state` commit。若只授權這次五張，結束立刻把 API variable 改回 `false`。
3. 取得後續授權後，可手動選 `max_items=500`、`reuse_existing`、一個日期窗；手動仍要勾 `authorization_ack`。初次建庫中不需要增量勾選；準備進入日期增量時，另行授權後勾 `incremental_authorization_ack`。選項也保留 25／50／100。手動沿用過期或缺少 snapshot 會停止，須明確改選 `refresh_all_nine`，不會自行擴大下載。
4. 確認發布兩個 variable 均為 `true`。Actions → **Build and approve TFDA Pages** → Run workflow：`app_ref=main`、`data_ref=data-state`（也可填已審查完整 SHA）。可邊建庫邊首次上線。
5. 等 build 的單元、Chromium、來源／資料及發布檢查全綠，打開 run summary 的主管摘要與 `release-audit-<run id>`，核對兩個完整 SHA、涵蓋、官方資料日期、缺件與同義詞。
6. 首次發布會停在 **`github-pages`**。使用者登入 GitHub，在該次 run 按 **Review deployments → 勾 github-pages → Approve and deploy**。有問題按 Reject。程式 SHA 改變及所有手動發布／回滾也走這個核准流程。
7. 部署後執行既有手機 Chromium smoke：核對 release ID、app/data SHA、涵蓋目錄、資料時間，並用正式藥證深連結搜尋。查看 `deployment-smoke-<run id>` 的 `ready=true`。
8. **人工核准的部署和 smoke 都成功後**，`record-approved-app` 才在 `data-state/approved-app.json` 寫入 app SHA、repository、`github-pages`、deployment run ID／attempt，並以獨立 commit 留證。到對應 run 可核對 environment 核准與 smoke。不要手動建立或修改這個檔；寫入失敗就仍視為待核准，下次手動發布重跑。它和 refresh 使用同一組 concurrency，避免互相覆寫。

## 每日補齊與自動發布

明確授權日更後，同時設 `TFDA_API_CALLS_AUTHORIZED=true`、`TFDA_SCHEDULE_AUTHORIZED=true`。每天 UTC `23 2 * * *`，即臺灣 **10:23** 執行（GitHub 排程可能延後）。排程取代手動勾選；缺任一授權都會在官方下載前停止。

排程固定初次建庫上限 500 張、間隔 2 秒、日期增量最多一個 10 日窗。沿用九來源 snapshot，只有缺少或年齡超過既有 14 天限制時自動重抓全部九來源；重抓失敗不提交半套資料。其他損壞或格式錯誤照樣停止。逐張與日期增量仍分兩階段：初次完成的那輪先存 checkpoint，下一輪才開始增量；一個日期窗的文件份數由 TFDA 決定，不受 500 張限制。保留 Retry-After、限速及續傳狀態。

只有成功的 **scheduled** refresh 會觸發發布。refresh 保存小型 `scheduled-refresh-revisions` artifact（只有 run ID、event、app/data SHA），部署核對同 repository、預設分支、成功 schedule run、不可變 SHA，並讀取當前 `data-state` 的最後人工核准紀錄。**同一個已核准 app SHA** 且所有檢查通過，才走無 reviewer 的 **`github-pages-auto`**。首次、SHA 改變或核准紀錄缺少／損壞，改走 reviewer；來源證據不符則直接停止。手動 refresh 不會觸發自動發布；自動部署不改寫核准紀錄。

停日更：把 `TFDA_SCHEDULE_AUTHORIZED=false`；停全部下載再把 `TFDA_API_CALLS_AUTHORIZED=false`。停發布：`PUBLICATION_AUTHORIZED=false`。這些鎖不會撤回已在進行中的請求／已發布網站；必要時在 Actions 取消正在執行的 run。

## 回滾與異常

從上一個正常 `release.json` 或 audit 找到 app/data 完整 SHA，手動執行發布並填入兩個 SHA，重新檢查、人工核准與 smoke。不 force push、不刪舊正常版本。smoke 失敗代表這次發布異常；網站已切換，不會自動回滾，應手動核准發布上一版。

網站每天按臺灣日期檢查官方 snapshot，超過 14 天、缺少日期或在未來會警告；重新建置不會把舊資料冒充新資料。`coverage.json` 保留缺件數，未有內文只連食藥署仿單頁，不保證官方頁有仿單。

本機本輪未呼叫網路、commit、push、配置 environment 或發布。正式排程、reviewer 與 Pages 須由 Claude／使用者照上述步驟驗收。
