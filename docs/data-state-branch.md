# TFDA 搜尋資料分支

這是 `data-state` 專用分支，不是網站程式碼分支。它只保存已完成一整批、已驗證且可續傳的官方公開資料。

- 不要直接編輯這個分支。
- 不要把病人資料、密碼或 token 放進來。
- `official/current/raw/` 是九組同一次驗證通過的官方原始 ZIP／JSON／CSV；不保存可由原始檔重建的 normalized 複本。
- `structured/` 是依藥證分片保存的結構化仿單與續傳狀態。
- `data-state-manifest.json` 記錄分母、完成數、涵蓋率與資料雜湊；產生前會重驗九個 raw，也會逐張核對 downloaded 狀態、分片路徑與內容藥證。
- `structured/state.json` 記錄逐藥證建庫；`structured/updates-state.json` 記錄下一個日期更新窗。發布時增量游標必須存在且最多落後 14 天；九來源 snapshot 也必須在 14 天內，兩者分開檢查。
- 沿用既有 snapshot 時，資料 workflow 會在任何仿單 API 請求前檢查 SHA、筆數、網址與年齡；超過 14 天時不執行仿單同步，必須重新選 `refresh_all_nine`。
- 更新工作中斷時不會 push，因此分支仍停在上一個完整 commit。
- 後續逐批補仿單預設沿用這個分支的九來源 snapshot；沿用前仍會完整重驗，不會每 25 張重複下載九份大型資料。
- commit 前會拒絕任何超過 95 MiB 的單一檔案，避免碰到 GitHub 一般 Git 單檔限制。

程式碼、操作說明與發布工作位於 `main` 分支。
