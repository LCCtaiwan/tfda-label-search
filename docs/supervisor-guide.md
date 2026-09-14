# 主管操作小抄

平常只需要看兩種工作：

1. `Refresh TFDA data state`：資料人員手動更新一小批。成功只代表資料保存完成，不會上線。
2. `Build and approve TFDA Pages`：先自動檢查，通過後才會請主管核准上線。

收到核准通知時，先看九件事：

先打開該次 Actions 的「TFDA Pages 主管核准摘要」。摘要不是自動批准；它只是把五份原始證據放在同一頁，數字互相對不上時工作會先停止。主管仍要下載 `release-audit-<run id>` 核對原始檔。

- `coverage.json` 的 `structured_coverage` 是否至少 98%。
- `coverage.json` 的 `metadata_only_with_official_files`、`metadata_only_without_official_files` 是否合理；後者突然增加就先拒絕。
- `synonyms.json` 是否只包含已確認的詞組，且每組都有審查人與審查日期；看不懂的詞不要核准。
- `verified-data-state.json` 的 `official_snapshot_age_days` 與 `incremental_lag_days` 是否都不超過 14，且 `incremental_initialized` 是否為 `true`。
- `manifest.json` 的 `ready` 是否為 `true`。
- `manifest.json` 的 `app_revision` 與 `data_revision` 是否是本次要發布的兩個 commit。
- `manifest.json` 的 `official_snapshot_id`、`data_retrieved_at` 與九個 `source_hashes` 是否存在。
- `publication-preflight.json` 的 `ready` 是否為 `true`，且網站頁尾有兩個提供機關與授權條款。
- Actions 的單元與 Chromium 測試是否全部綠色。

九項都正確才按 `Approve and deploy`；看不懂、數字突然下降或來源失敗就按 `Reject`，舊網站會繼續使用。部署完成後再確認 `deployment-smoke-<run id>` 的 `ready` 是 `true`，且兩個 SHA 與核准版本相同；失敗時依部署手冊回滾。

平常打開網站若看到紅色「官方資料已超過 14 天沒有更新」或「無法確認官方資料更新日期」，先停止把它當成最新資料，檢查資料 workflow。只重新部署同一份舊資料不會消除警告。

本網站只查公開藥品資料，不可加入病人姓名、病歷號、處方或其他病人資料。

第一次執行資料工作要選 `refresh_all_nine` 與 25 張，勾選 `authorization_ack`，但不要勾 `incremental_authorization_ack`。之後逐批補仿單用預設 `reuse_existing`。每一次都必須重新勾選本輪真正獲准的項目，不能只靠長期 repository variable。若預檢說 snapshot 超過 14 天，改選 `refresh_all_nine`；系統會在任何仿單 API 前停止，所以不會浪費 25 次請求。

初次建庫完成後，日期增量要另外取得授權才勾選 `incremental_authorization_ack`。`max_update_windows=1` 代表最多查一個 10 日窗，不代表最多 25 份；該窗回傳幾份由 TFDA 決定。沒有勾選時，程式會在日期 API 前停止。

若要確認「官方仿單檔案」連結實際是 PDF、圖片還是網頁，也要另外批准一次小量抽查。抽查只讀檔頭，不保存檔案；看到 PDF 檔頭仍不能宣稱整份 PDF 已完整可讀。
