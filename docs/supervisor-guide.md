# 主管操作小抄

平常只需要看兩種工作：

1. `Refresh TFDA data state`：資料人員手動更新一小批。成功只代表資料保存完成，不會上線。
2. `Build and approve TFDA Pages`：先自動檢查，通過後才會請主管核准上線。

收到核准通知時，先看三件事：

- `coverage.json` 的 `structured_coverage` 是否至少 98%。
- `manifest.json` 的 `ready` 是否為 `true`。
- Actions 的單元與 Chromium 測試是否全部綠色。

三項都正確才按 `Approve and deploy`；看不懂、數字突然下降或來源失敗就按 `Reject`，舊網站會繼續使用。

本網站只查公開藥品資料，不可加入病人姓名、病歷號、處方或其他病人資料。
