# 開發紀錄

## Current Goal

建立獨立、可正式上線且可交接的「TFDA仿單搜尋」成品。第一個可驗證功能成果是 Pagefind 小型概念驗證：以真實結構化仿單章節證明繁體中文短詞、英文、結果原文及來源資訊可以在 GitHub Pages 架構中正確運作。

## Stack And Run Commands

預定技術：

- 靜態前端：HTML、CSS、JavaScript。
- 資料更新：Python 3、GitHub Actions。
- 全文搜尋：Pagefind。
- 發布：GitHub Pages。

實際使用命令：

```sh
npm install --cache .npm-cache
npm test
npm run build -- \
  --input tests/fixtures/pagefind-search-sample.json \
  --input tests/fixtures/structured-real-sample.json \
  --output site
npm run serve
```

## Decisions

- TFDA 仿單、全臺健保及安全資訊已超出化療調配專案範圍，因此建立獨立專案。
- 健保資料仍與藥證及仿單密切相關，保留為本專案的輔助資料，不再拆成第三個網站。
- `chemodrugstable-query` 保持不變；新網站日後以網址參數接收藥名、藥證或健保碼。
- Pagefind 是第一個正式候選搜尋層，必須以真實資料驗證，不能只依官方說明認定可行。
- 結構化電子仿單為主要文字來源；PDF 或圖片只作可追溯備援。
- 任意關鍵字搜尋至少支援中文二字詞；規格中的三個詞只是驗收樣本。
- 原作者已表示同意使用 `TFDA-drug-info-search`，但正式移植前仍應保存同意範圍及署名方式。
- 未經另外明確授權，不推送、部署、建立付費資源或大量呼叫官方 API。

## Completed Work

### 2026-09-15：專案規格確認

- 確認專案名稱、使用者、輸入、輸出、第一版範圍、不納入項目與成功證據。
- 確認新專案位置為 `/Users/lcc/Desktop/PGY許願池/tfda-label-search`。
- 建立 `SPEC.md`，並補充「噁心、懷孕、腎功能不全」只是驗收範例。
- 建立專案文件骨架；功能程式尚未開始移植。

### 2026-09-15：C-002 小型 Pagefind 概念驗證

- 完成來源檔案盤點，先移植結構化仿單解析與官方來源驗證；未帶入 Supabase／PGroonga。
- Pagefind 以「一個仿單章節一筆記錄」建索引。第一次瀏覽器測試發現同一藥品的章節共用官方網址時會被合併，已改成每章使用唯一索引網址，官方網址另以受控 metadata 保存。
- 索引輸出只包含清理後純文字，不保存內嵌圖片或 Base64 內容。
- 同義詞檔目前為空；只有人工審查並標示 `reviewed: true` 的詞組才會生效。

### 2026-09-15：C-003 靜態 release 與健保連接

- 以有效藥證清單作分母，將九組官方來源快照與結構化仿單整理成不可變 release。
- 健保碼只在官方健保品項 URL 的 `licId` 能唯一對上有效藥證時自動連接；缺少、找不到或多重對應都不猜測。
- 尚無結構化文字的有效藥證仍可由藥名、成分或健保碼找到，但清楚標示為 metadata-only。
- 第一次健保碼畫面測試發現 metadata 放在每個章節會產生 50 筆同藥結果，已拆成每藥一筆 metadata record，章節索引只保存章節文字。
- `active.json` 只在候選 release 完成所有驗證後原子切換；測試確認涵蓋率失敗不改動舊指標。

## Verification Status

- 規格：使用者已確認。
- Python：19 個測試通過。
- Node.js：Pagefind 建置測試通過。
- 小型索引：4 份文件、54 個章節，整個靜態網站約 876 KB，其中 Pagefind 約 820 KB。
- 真實瀏覽器：`噁心` 3 筆、`懷孕` 2 筆、`腎功能不全` 2 筆；`懷孕 AND 噁心` 1 筆；`噁心 NOT 腹瀉` 2 筆；`腹瀉 OR 腎功能不全` 3 筆。
- 章節展開後會載入原文；桌機 1440×1000 與手機 390×844 版面通過目視檢查；主控台 0 錯誤。
- Release 瀏覽器驗證：健保碼 `A016162100` 只回 1 張正確藥品資料卡，並顯示成分、ATC、仿單版本及官方入口；主控台 0 錯誤。
- 線上服務：未建立或修改。
- 既有 ChemoDrugStable：未修改。

## Recommended Next Step

補上受控的官方批次下載及結構化仿單增量／續傳，再進行 1,000 至 5,000 份代表性容量試驗。
