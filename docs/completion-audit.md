# Goal 完成度稽核

稽核日期：2026-09-15。`pass` 代表已有直接證據；`partial` 代表本機能力完成但缺正式外部驗證；`blocked` 代表必須取得使用者授權或外部資訊，不能自行代替。

| Goal 要求 | 狀態 | 直接證據 | 尚缺什麼 |
|---|---|---|---|
| 獨立專案，保留 ChemoDrugStable | pass | 本專案位於 `/Users/lcc/Desktop/PGY許願池/tfda-label-search`，有獨立 Git 歷史；來源與 `chemodrugstable-query` 未修改 | 無 |
| TFDA／健保九來源下載、格式與來源追溯 | pass（本機） | `tools/sources/official.py`、`official_sources.json`、來源網域／欄位／最低筆數／雜湊測試 | 正式九來源 workflow 尚未在 GitHub 執行 |
| TFDA 結構化電子仿單 API | pass（本機） | 藥證／健保碼／10 日窗、Base64 文字、階層章節、圖片排除、64 MiB 上限、Retry-After 與失敗保留測試 | 官方未公布可接受請求頻率 |
| 版本發布與失敗保護 | pass（離線） | 不可變 release、active 指標、來源失敗、涵蓋率失敗、同 ID 覆寫拒絕、完整 `data-state → candidate Pages` 演練 | 尚未對真正的 GitHub environment 做中斷／回滾演練 |
| Pagefind 任意中文與英文 | pass（fixtures） | Chromium 自動查詢「噁心、懷孕、腎功能不全、Nausea」及 5000 份容量搜尋 | 仍需長短不同真實仿單的召回品質抽查 |
| 藥名、成分、藥證、健保碼 | pass（fixtures） | 精確 metadata 目錄、健保唯一藥證連接、完整中文藥證與去重 Chromium 測試 | 仍需正式全量健保連接報告 |
| AND／OR／NOT、人工同義詞、分批結果 | pass（fixtures） | 5 個 Chromium 測試含 AND／OR／NOT、只接受 `reviewed: true`、50→100 筆 | 正式同義詞檔仍為空，需藥師核准第一組詞 |
| 顯示章節、原文、版本、日期與官方來源 | pass（fixtures） | 結果卡、可展開原文、TFDA HTTPS 白名單、頁尾資料日期／份數／SHA-256 指紋測試 | 正式站仍需人工抽查官方連結 |
| 代表性容量與繁中短詞 | partial | 1000／5000 份合成容量通過；5000 份 103 MB；繁中短詞與手機資源量測完成 | Goal 明訂的 1000–5000 份「長短不同真實代表性仿單」尚未取得，因此不可判定完成 |
| 資料品質與安全 | pass（本機） | 官方主機白名單、回應大小、ZIP 解壓大小、CSP、純文字呈現、無病人資料、來源／涵蓋率 gate | 正式公開前仍需確認仿單文字與圖片重製邊界 |
| GitHub Actions 與 Pages | partial | 三份 YAML 可解析；CI、手動 `data-state`、98% gate、Pages artifact、部署鎖均已寫好 | 尚未建立遠端、推送、設定 required reviewer 或實際部署 |
| 桌機與手機端到端 | pass（本機） | Chromium 5 項自動測試、390×844 視窗、主控台 0 錯誤；先前桌機目視驗證 | 正式網址上線後需再跑同組測試 |
| 部署與主管交接 | pass（文件） | `docs/deployment.md`、`docs/supervisor-guide.md`、共享 Claude handover #181 | 主管帳號與實際核准責任尚未指定 |
| 原作者同意範圍 | partial | 目前只採獨立網站、靜態快取與呈現概念，沒有直接複製第三方程式碼 | 可修改、公開部署、再散布及署名內容仍需保存成可交接文字 |

## 已執行的驗證

```text
npm test                    31 passed（29 Python + 2 Node）
npm run test:e2e             5 passed（Chromium）
offline deployment rehearsal 1 passed（已包含在 Python 測試）
workflow YAML parse          3 passed
5000-document build          103 MB，最近一次 23.23 秒
```

## 現在不能宣稱的事

- 不能宣稱已正式上線，因為沒有遠端與 Pages deployment。
- 不能宣稱涵蓋全臺仿單，因為沒有正式全量資料與涵蓋率報告。
- 不能把合成 5000 份測試說成真實代表性資料驗證。
- 不能宣稱 TFDA 同意每 2 秒一個請求；這只是保守預設。
- 不能宣稱主管核准已存在；workflow 的變數鎖仍需在 GitHub 設定後實測。

## Goal 完成前的必要門檻

1. 使用者授權建立新遠端、推送及第一次 25 張正式小批。
2. 指定 repository 擁有者、公開／私人設定與主管 GitHub 帳號。
3. 保存原作者同意與官方重製邊界的文字證據。
4. 以 1000–5000 份長短不同真實仿單重跑容量、搜尋品質、涵蓋率與手機驗證。
5. 設定 required reviewer 後完成一次候選拒絕、一次主管核准與一次 Pages 回滾演練。
