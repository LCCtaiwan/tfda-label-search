# Goal：結構化電子仿單第一輪實測（2026-11-25）

使用者已授權：建公開 repo `LCCtaiwan/tfda-label-search`、推送分支、從 GitHub Actions 呼叫食藥署 API 實測。

分工：程式修改由 Codex 做；驗收、git commit、GitHub 操作由 Claude 做。

## 完成標準

| # | 項目 | 誰 | 驗收方式 |
|---|---|---|---|
| 1 | `air/structured-only`：發布資料與網頁不含 PDF／官方檔案連結；無結構化文字的藥證只連 `https://mcp.fda.gov.tw/im_detail_1/<許可證>`；涵蓋分類改為「有結構化仿單文字／尚無結構化仿單（連食藥署仿單頁）」 | Codex | 審 diff；在建置輸出搜尋 `pdf`、`exportpdf`、`pdfcasefile` 為零 |
| 2 | 全部離線測試通過（Python、Node；可離線時含 Chromium） | Codex | Claude 自行重跑 |
| 3 | `refresh-data.yml` 的 `max_items` 加入 `"5"` 選項（其餘授權關卡不變） | Codex | 審 diff |
| 4 | 驗收通過後 commit | Claude | `git log` |
| 5 | 公開前掃描機密與大檔；建公開 repo，推送 `main` 與 `air/structured-only`；CI 通過 | Claude | `gh run list` |
| 6 | 設 repo 變數 `TFDA_API_CALLS_AUTHORIZED=true`，在 `air/structured-only` 手動執行 refresh-data：`max_items=5`、`official_source_mode=refresh_all_nine`、`max_update_windows=1`、`authorization_ack=true`、`incremental_authorization_ack=false` | Claude | run 結果、附件 |
| 7 | 實測後把 `TFDA_API_CALLS_AUTHORIZED` 改回 `false` | Claude | `gh variable list` |
| 8 | 回報：GitHub Actions 能否呼叫 `GetDrugDoc`、5 張中幾張有結構化仿單、回應大小與耗時、`data-state` commit | Claude | 報告 |

## 不做

發布 GitHub Pages、開排程、日期增量、超過 5 張逐張查詢、PDF 任何用途。
