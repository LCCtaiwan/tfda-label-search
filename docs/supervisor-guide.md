# 主管操作小抄

平常只需要看兩種工作：

1. `Refresh TFDA data state`：資料人員手動更新一小批。成功只代表資料保存完成，不會上線。
2. `Build and approve TFDA Pages`：先自動檢查，通過後才會請主管核准上線。

收到核准通知時，先看九件事：

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

第一次執行資料工作要選 `refresh_all_nine` 與 25 張；之後逐批補仿單用預設 `reuse_existing`。每一次都必須勾選 `authorization_ack`，不能只靠長期存在的 repository variable 代表本次已獲准。
