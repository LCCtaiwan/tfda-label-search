# GitHub Pages 部署

## 為什麼分成兩條工作

`refresh-data.yml` 只下載與保存資料，永遠不部署網站。`deploy-pages.yml` 只讀取已提交的 `data-state`，重新驗證、建置及測試；最後仍需主管核准。任何下載或建置失敗都不會改掉目前網站。

GitHub Actions cache 不是權威資料庫，因為未使用的 cache 可能被移除。`data-state` 分支以 Git commit 作為完整批次的單一指標；工作中斷時沒有 commit，也就沒有半套資料成為最新版。分支只保存官方原始檔、狀態與結構化仿單，不重複保存 normalized 資料；任何單檔超過 95 MiB 時會在 commit 前停止。

95 MiB 是本專案保守設定的緩衝線，不是宣稱 GitHub 官方上限正好是 95 MiB。若正式原始檔超過這條線，先停止更新並評估 Git LFS 或物件儲存；不要繞過檢查硬推。`data-state-manifest.json` 會記錄檔案數、總容量與最大檔案。

## 一次性設定

1. 建立新的 GitHub repository，推送 `main`。不要沿用 `chemodrugstable-query`。
2. Repository Settings → Pages → Source 選 `GitHub Actions`。
3. Repository Settings → Environments → `github-pages`。
4. 加入主管為 Required reviewer，並勾選 Prevent self-review。
5. 確認 Required reviewer 已生效後，建立 Repository variable：`SUPERVISOR_APPROVAL_CONFIGURED=true`。
6. 專案負責人明確同意官方小批流程後，才設定 `TFDA_API_CALLS_AUTHORIZED=true`；每次執行仍須另外勾選本輪授權確認。
7. 專案負責人明確同意公開網站後，才設定 `PUBLICATION_AUTHORIZED=true`。

若是 GitHub Free，Required reviewer 只適用公開 repository。若單位要求 private repository，必須先確認目前方案支援；不可只把變數設為 true 來假裝有主管核准。

## 初次資料建立

1. 到 Actions 執行 `Refresh TFDA data state`。
2. 第一次選 `max_items=25`、`official_source_mode=refresh_all_nine`，並勾選 `authorization_ack`。若第一次仍選預設的 `reuse_existing`，系統會因為沒有既有 snapshot 而停止。
3. 後續逐批補仿單時保留 `official_source_mode=reuse_existing`，避免重複下載九個大型來源；每次仍要勾選 `authorization_ack`。
4. 只有要取得新版藥證、成分、健保或安全資料時才選 `refresh_all_nine`。無論沿用或重抓，九來源都會在任何仿單 API 請求前重新驗證。
5. 確認 TFDA 無 429、逾時或阻擋後，再由負責人決定是否使用 50 或 100。
6. 每次成功會在 `data-state` 新增一個 commit；失敗不會 push。查看 run summary 的來源模式、`official-preflight`、`pending_licenses`、`checked_coverage` 與 `structured_coverage`。
7. 初次逐藥證完成的那一輪會先保存 checkpoint；再執行一次後才開始最多 1／2／3 個 10 日增量窗，並在 summary 顯示 `phase`、`next_date` 與 `remaining_days`。
8. 重複執行到資料符合發布門檻。官方尚未公布頻率，因此不可自行增加排程或把間隔調短。

## 建置與核准

1. 到 Actions 手動執行 `Build and approve TFDA Pages`。
2. 一般發布使用 `app_ref=main`、`data_ref=data-state`；workflow 會先把兩者解析成不可變的完整 commit SHA。
3. 工作會重跑單元測試、Chromium 測試，並重新解析九個 raw 檔、核對 snapshot 網址／SHA-256／筆數、逐張核對 downloaded 仿單，再檢查 98% 結構化文字門檻與最多 14 天的日期增量落後。
4. 工作會檢查 `config/publication-policy.json` 與網站可見署名，產生 `publication-preflight.json`；權利範圍或署名不完整就停止。
5. 通過後進入 `github-pages` environment 等待主管。
6. 主管查看 `release-audit-<run id>` 的報告、公開 `synonyms.json` 與兩個 commit SHA，再按 Approve and deploy 或 Reject。
7. 部署後會用相同 app SHA 的檢查器，以 390×844 Chromium 開啟正式網址，逐字核對 release ID 與本次核准的完整 app/data SHA，檢查 snapshot 與資料時間，再從正式目錄選一張完整藥證，以 `?q=<完整藥證>` 深連結自動搜尋；結果保存為 `deployment-smoke-<run id>`。

網站即使沒有重新部署，也會在每次開啟時依臺灣日期重算資料年齡。超過 14 天、日期缺少或日期晚於今天會在頁面頂端警告；主管仍應查明更新失敗原因，不能只重新建置網站來清除警告。

## 回滾

- 從上一個正常的 release audit 或 `site/data/release.json` 找到 `app_revision` 與 `data_revision`。
- 重新執行 `Build and approve TFDA Pages`，將 `app_ref`、`data_ref` 填入這兩個完整 SHA。
- 系統會重新建置，不會修改舊 commit；主管仍要核准，部署後仍會執行 smoke test。
- 只選擇曾經由本流程成功發布、具有 `release.json` 的版本；C-011 之前的本機原型不是正式回滾目標。
- smoke test 若失敗，先將該次 run 視為異常，再依上面步驟發布上一個正常版本。GitHub Pages 已切換的內容不會被檢查器自行刪除。
- 不使用 `git push --force`。不刪除舊的正常 Pages deployment 或資料 commit。

## 目前不會自動發生的事

- 兩個 workflow 都只允許手動啟動，尚未排程。
- 本機建立這些檔案不等於已建立 repository、environment、變數或 Pages 網站。
- 未經明確授權，不推送、不部署，也不啟動正式大量 TFDA API 呼叫。
- `TFDA_API_CALLS_AUTHORIZED` 與 `PUBLICATION_AUTHORIZED` 沒有設為 `true` 時，workflow 會明確失敗，不會把「能按按鈕」當成「已獲授權」。
- 所有 GitHub 官方 Actions 都固定到 2026-09-15 查得的官方 release 完整 commit SHA；升級時須重新查官方 release、更新註解並通過 workflow guard 測試。

## GitHub 官方依據

- Pages 限制：https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- 自訂 Actions 發布 Pages：https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Environment 與 required reviewer：https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- Actions cache 淘汰規則：https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
- Repository 單一物件與整體大小建議：https://docs.github.com/en/repositories/creating-and-managing-repositories/repository-limits
