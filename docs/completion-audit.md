# Goal 完成度稽核

稽核日期：2026-09-15。`pass` 代表已有直接證據；`partial` 代表本機能力完成但缺正式外部驗證；`blocked` 代表必須取得使用者授權或外部資訊，不能自行代替。

| Goal 要求 | 狀態 | 直接證據 | 尚缺什麼 |
|---|---|---|---|
| 獨立專案，保留 ChemoDrugStable | pass | 本專案位於 `/Users/lcc/Desktop/PGY許願池/tfda-label-search`，有獨立 Git 歷史；來源與 `chemodrugstable-query` 未修改 | 無 |
| TFDA／健保九來源下載、格式與來源追溯 | pass（本機） | `tools/sources/official.py`、`official_sources.json`；部署前逐一重算並核對九個 raw 的來源網址、SHA-256、原始與整理筆數 | 正式九來源 workflow 尚未在 GitHub 執行 |
| TFDA 結構化電子仿單 API | pass（本機） | 藥證／健保碼／10 日窗、初始→增量自動切換、臺灣完整日游標、no-document 提升、新舊版防倒退、圖片排除、64 MiB 上限、Retry-After 與失敗保留測試 | 官方未公布可接受請求頻率 |
| 版本發布與失敗保護 | pass（離線） | 不可變 release、九 raw 重驗、每張 downloaded 檔案對應、程式／資料完整 SHA 身分證、指定舊 SHA 回滾入口、完整 `data-state → candidate Pages` 演練 | 尚未對真正的 GitHub environment 做拒絕／回滾演練 |
| Pagefind 任意中文與英文 | pass（fixtures） | Chromium 自動查詢「噁心、懷孕、腎功能不全、Nausea」及 5000 份容量搜尋 | 仍需長短不同真實仿單的召回品質抽查 |
| 藥名、成分、藥證、健保碼 | pass（fixtures） | 精確 metadata 目錄、健保唯一藥證連接、完整中文藥證與去重 Chromium 測試；健保品項折疊顯示支付價、有效期間、規格、劑型、藥商、給付章節及白名單官方連結 | 仍需正式全量健保連接報告，並核對實際網址與日期品質 |
| 網址深連結與跨站導流 | partial | `q`／`any`／`exclude` 可自動搜尋並同步分享網址；相容 `all`／`not`；Chromium 已驗證完整藥證、AND／OR／NOT 與過大輸入拒絕 | 正式 Pages 網址尚未建立，因此尚未修改或實測 ChemoDrugStable 連結 |
| AND／OR／NOT、人工同義詞、分批結果 | pass（fixtures） | 9 個 Chromium 測試含 AND／OR／NOT、50→100 筆；同義詞建置會要求審查人／日期、拒絕重複與衝突、排除草稿，且英文大小寫正規化已實測 | 正式同義詞檔仍為空，需藥師核准第一組詞 |
| 顯示章節、原文、版本、日期與官方來源 | pass（fixtures） | 結果卡、可展開原文、TFDA HTTPS 白名單、頁尾資料日期／份數／SHA-256；metadata-only Chromium 驗證官方仿單檔案按鈕 | 正式站仍需人工抽查官方連結 |
| 回收、警示、風險管理與短缺關聯 | pass（fixtures） | 結果卡折疊顯示日期、標題、狀態及 TFDA 資料集來源；明示不是目前狀態，且不加入仿單全文索引；未知類型或外站網址會拒絕建置 | 仍需用獲准正式小批核對九來源實際欄位與官方最新內容 |
| 資料涵蓋與缺件報告 | partial | release 與公開 `data/coverage.json` 分開計算有可搜尋文字、只有官方檔案、文字與檔案皆無；頁面與部署 smoke 都會交叉核對總數；Chromium 已驗證可見摘要 | 尚未取得正式資料，不能區分實際可讀 PDF、圖片或失效連結，也不能產生全臺真實涵蓋率 |
| 代表性容量與繁中短詞 | partial | 1000／5000 份合成容量通過；5000 份 103 MB；繁中短詞與手機資源量測完成 | Goal 明訂的 1000–5000 份「長短不同真實代表性仿單」尚未取得，因此不可判定完成 |
| 資料品質、安全與公開使用邊界 | pass（本機） | 官方主機白名單、回應／ZIP 上限、CSP、無病人資料、純文字限定、圖片／PDF／標誌排除、官方授權證據與可見署名 preflight；瀏覽器每天重算資料年齡，超過 14 天或日期不可信會警告 | 若日後擴大發布素材範圍，必須重新確認權利 |
| GitHub Actions 與 Pages | partial | 三份 YAML 可解析；官方 Actions 固定完整 SHA；資料工作預設 25 張、本輪授權確認、九來源重用、仿單 API 前 14 天快照預檢、初始／增量協調、部署時九來源 snapshot 與仿單增量各自 14 天 gate、98% gate、95 MiB 保護、雙鎖、同版檢查器與完整 SHA smoke 均已寫好 | 九來源未提供可用的 HTTP 檔案大小；尚未建立遠端、推送、設定 required reviewer 或實際部署 |
| 桌機與手機端到端 | pass（本機） | Chromium 10 項自動測試；另以 390×844 smoke 核對 release、完整藥證 1 筆、主控台 0 錯誤 | 正式網址上線後需由同一工具重跑 |
| 部署與主管交接 | pass（文件） | `docs/deployment.md`、`docs/supervisor-guide.md`、專案共享 handover | 主管帳號與實際核准責任尚未指定 |
| 原作者同意範圍 | pass（目前成品） | 已記錄 `liangRXdev/TFDA-drug-info-search`；目前只採需求概念，`copied_files` 為空，未直接納入第三方程式 | 未來若直接複製程式，preflight 會要求同意紀錄、署名與檔案清單 |

## 已執行的驗證

```text
npm test                    69 passed（58 Python + 11 Node）
npm run test:e2e            10 passed（Chromium）
offline deployment rehearsal 1 passed（已包含在 Python 測試）
workflow YAML parse          3 passed
npm audit                    0 vulnerabilities
publication preflight        ready: true，8 checks
local deployment smoke       ready: true，release／兩個完整 SHA／snapshot／資料時間／114 份涵蓋相符，q 深連結完整藥證 1 筆，console 0
5000-document build          103 MB，最近一次 23.23 秒
```

## 現在不能宣稱的事

- 不能宣稱已正式上線，因為沒有遠端與 Pages deployment。
- 不能宣稱涵蓋全臺仿單，因為沒有正式全量資料與涵蓋率報告。
- 不能把「有官方檔案連結」說成已確認可讀 PDF 或圖片；尚未取得檔案內容驗證。
- 不能把合成 5000 份測試說成真實代表性資料驗證。
- 不能宣稱 TFDA 同意每 2 秒一個請求；這只是保守預設。
- 不能宣稱主管核准或使用者公開授權已存在；workflow 的變數鎖仍需在 GitHub 設定後實測。

## Goal 完成前的必要門檻

1. 使用者授權建立新遠端、推送及第一次 25 張正式小批。
2. 指定 repository 擁有者、公開／私人設定與主管 GitHub 帳號。
3. 以 1000–5000 份長短不同真實仿單重跑容量、搜尋品質、涵蓋率與手機驗證。
4. 設定 required reviewer 後完成一次候選拒絕、一次主管核准與一次 Pages 回滾演練。
