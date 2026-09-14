# GitHub Pages 部署

## 為什麼分成兩條工作

`refresh-data.yml` 只下載與保存資料，永遠不部署網站。`deploy-pages.yml` 只讀取已提交的 `data-state`，重新驗證、建置及測試；最後仍需主管核准。任何下載或建置失敗都不會改掉目前網站。

GitHub Actions cache 不是權威資料庫，因為未使用的 cache 可能被移除。`data-state` 分支以 Git commit 作為完整批次的單一指標；工作中斷時沒有 commit，也就沒有半套資料成為最新版。

## 一次性設定

1. 建立新的 GitHub repository，推送 `main`。不要沿用 `chemodrugstable-query`。
2. Repository Settings → Pages → Source 選 `GitHub Actions`。
3. Repository Settings → Environments → `github-pages`。
4. 加入主管為 Required reviewer，並勾選 Prevent self-review。
5. 確認 Required reviewer 已生效後，建立 Repository variable：`SUPERVISOR_APPROVAL_CONFIGURED=true`。

若是 GitHub Free，Required reviewer 只適用公開 repository。若單位要求 private repository，必須先確認目前方案支援；不可只把變數設為 true 來假裝有主管核准。

## 初次資料建立

1. 到 Actions 執行 `Refresh TFDA data state`。
2. 第一次先選 25；確認 TFDA 無 429、逾時或阻擋後，再由負責人決定是否使用 50 或 100。
3. 每次成功會在 `data-state` 新增一個 commit；失敗不會 push。
4. 查看 run summary 的 `pending_licenses`、`checked_coverage` 與 `structured_coverage`。
5. 重複執行到資料符合發布門檻。官方尚未公布頻率，因此不可自行增加排程或把間隔調短。

## 建置與核准

1. 到 Actions 手動執行 `Build and approve TFDA Pages`。
2. 工作會重跑單元測試、Chromium 測試、九來源驗證與 98% 結構化文字門檻。
3. 通過後進入 `github-pages` environment 等待主管。
4. 主管查看 `release-audit-<run id>` 的 `manifest.json` 與 `coverage.json`，再按 Approve and deploy 或 Reject。

## 回滾

- 網站內容有問題：在 GitHub Pages deployment history 選擇上一個正常部署，或由上一個程式／資料 commit 重跑建置。
- 資料有問題：不要改壞 commit；從 `data-state` 的上一個正常 commit 建立修正 commit，再重新建置與核准。
- 不使用 `git push --force`。不刪除舊的正常 Pages deployment 或資料 commit。

## 目前不會自動發生的事

- 兩個 workflow 都只允許手動啟動，尚未排程。
- 本機建立這些檔案不等於已建立 repository、environment、變數或 Pages 網站。
- 未經明確授權，不推送、不部署，也不啟動正式大量 TFDA API 呼叫。

## GitHub 官方依據

- Pages 限制：https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- 自訂 Actions 發布 Pages：https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- Environment 與 required reviewer：https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
- Actions cache 淘汰規則：https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching
