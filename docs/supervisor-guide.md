# 主管操作小抄

首次上線與程式 SHA 改變，需要使用者本人核准；同一個已核准程式的成功排程資料更新，通過全部檢查後可自動上線。手動發布與回滾一律人工核准。設定與完整步驟見 [部署手冊](deployment.md)。

Claude 先在 repository 設以下項目：

- Pages Source：`GitHub Actions`。
- Repository variables：`TFDA_API_CALLS_AUTHORIZED=true`（下載）、`TFDA_SCHEDULE_AUTHORIZED=true`（日更，五張試跑時先 `false`）、`SUPERVISOR_APPROVAL_CONFIGURED=true`（reviewer 確實生效後）、`PUBLICATION_AUTHORIZED=true`（同意公開後）。
- 可選 repository secret：`FORMULARY_CSV_URL`，HTTPS UTF-8 CSV，含 `藥名,ATC碼,狀態`。停用列不使用；CSV 只在記憶體排優先順序，不上傳清單，只留各層合計。失敗照原順序。
- `github-pages` environment：Required reviewers 設 `LCCtaiwan`（使用者本人），**Prevent self-review 不勾選**，讓本人可核准自己發起的 run。
- `github-pages-auto` environment：不設 reviewer 或 wait timer，允許預設分支部署；兩個 environment 都要允許 Pages。確認 Actions token 可正常寫入 `data-state`。

第一次資料工作選 5 張、`refresh_all_nine`、一個日期窗，勾 `authorization_ack`，不勾 `incremental_authorization_ack`。手動後續 500 張可選 `reuse_existing`，仍要逐次勾本輪授權；若超過 14 天，明確改選 `refresh_all_nine`。初次完成後要進日期增量，必須另行勾選增量授權；一窗最多 10 日，回傳份數由官方決定。

首次發布：Actions → `Build and approve TFDA Pages` → Run workflow，`app_ref=main`、`data_ref=data-state`。等待 build 全綠並出現 `github-pages` 待核准，再打開 run summary 的「TFDA Pages 主管核准摘要」及 `release-audit-<run id>`。請確認：

- `coverage.json` 有效藥證、有文字與尚無文字數量一致；**沒有 98% 下限，可在建庫中上線**。畫面應顯示「逐步補齊中」、X／Y／百分比與最後更新日。
- 九來源 SHA／筆數通過、snapshot 不超過 14 天；已存在的增量游標也不得落後超過 14 天。初次未完成可暫無游標；完成後缺游標則先跑一次授權增量。
- `manifest.json` 的 `ready=true`，app/data 完整 SHA、snapshot、官方資料日期符合本次預期。
- 公開同義詞都有審查人與日期；`publication-preflight.json` 為 `ready=true`、署名完整；所有單元與 Chromium 檢查綠色。無 PDF 內容或檔案備援，缺件只連指定食藥署仿單頁。

確認後，在 GitHub 該次 run 按 **Review deployments → 勾 github-pages → Approve and deploy**。異常或看不懂先按 Reject。部署後看 `deployment-smoke-<run id>` 的 `ready=true`，再確認 `record-approved-app` 成功；它會在 `data-state/approved-app.json` 留下核准 app SHA 與可追查 run ID，請勿手動修改。

每日排程為臺灣 10:23（可能延後），固定 500 張初次查詢或一個增量日期窗、每 2 秒一次，缺少／過期 snapshot 才自動重抓九來源；要兩個 TFDA 授權變數都開啟。成功後，只有與最後人工核准相同 app SHA 才進 `github-pages-auto`；程式改變會再次請本人核准。停日更設 `TFDA_SCHEDULE_AUTHORIZED=false`；停發布設 `PUBLICATION_AUTHORIZED=false`。

紅色資料過期警告、smoke 失敗或筆數異常時，先檢查 Actions；只重建舊資料不會解除過期。回滾用手動發布舊 app/data SHA，仍需本人核准。

本網站只查公開藥品資料，不可加入病人資料。食藥署仿單頁不保證有仿單；搜尋命中不代表因果、適用、禁用、互換或符合健保給付。
