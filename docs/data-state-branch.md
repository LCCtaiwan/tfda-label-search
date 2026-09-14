# TFDA 搜尋資料分支

這是 `data-state` 專用分支，不是網站程式碼分支。它只保存已完成一整批、已驗證且可續傳的官方公開資料。

- 不要直接編輯這個分支。
- 不要把病人資料、密碼或 token 放進來。
- `official/current/raw/` 是九組同一次驗證通過的官方原始 ZIP／JSON／CSV；不保存可由原始檔重建的 normalized 複本。
- `structured/` 是依藥證分片保存的結構化仿單與續傳狀態。
- `data-state-manifest.json` 記錄分母、完成數、涵蓋率與資料雜湊。
- 更新工作中斷時不會 push，因此分支仍停在上一個完整 commit。
- commit 前會拒絕任何超過 95 MiB 的單一檔案，避免碰到 GitHub 一般 Git 單檔限制。

程式碼、操作說明與發布工作位於 `main` 分支。
