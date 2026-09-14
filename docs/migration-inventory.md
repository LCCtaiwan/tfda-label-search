# 移植盤點

來源工作副本：`/Users/lcc/Desktop/PGY許願池/TFDA仿單搜尋`

目標專案：`/Users/lcc/Desktop/PGY許願池/tfda-label-search`

本清單只描述程式去向，不代表已建立遠端、推送、部署或執行正式全量下載。

## 立即移植

| 範圍 | 來源 | 理由 | 狀態 |
| --- | --- | --- | --- |
| 結構化電子仿單 | `tools/inserts/tfda_structured.py` | 直接使用 TFDA `GetDrugDoc`，保留章節、版本、原文及原子寫入保護 | 已移植 |
| 結構化仿單測試 | `tests/test_inserts_structured.py` | 驗證藥證／健保碼、10 日限制、巢狀章節、圖片排除與失敗保留舊檔 | 已移植 |
| 官方資料下載與正規化 | `tools/sources/official.py` | 提供官方網域限制、欄位與最低筆數檢查、內容雜湊及原子輸出 | 已移植 |
| 九個官方來源設定 | `tools/sources/official_sources.json` | 保留 TFDA、健保署固定來源與欄位契約 | 已移植 |
| 官方來源測試 | `tests/test_official_sources.py` | 驗證網址、日期、藥證、空短缺、欄位變動與重試 | 已移植 |

## 下一階段移植並改寫

| 範圍 | 來源 | 處理方式 |
| --- | --- | --- |
| 完整更新流程 | `tools/pipeline/update_release.py` | 保留增量日期、續傳與九來源品質門檻；移除 PostgreSQL release CLI 相依，改輸出不可變靜態 release |
| 健保資料 | `tools/nhi/` | 保留官方下載、日期與藥證連接；輸出 Pagefind metadata／filters，不再產生化療專案頁面 |
| 搜尋網站 | `inserts/` | 保留安全呈現、警語、網址狀態與行動版設計；把 Supabase RPC 改為 Pagefind Search API |
| 自動更新 | `.github/workflows/update-tfda-search.yml` | 改成建置靜態 release、Pagefind 索引、驗證後發布 GitHub Pages artifact |
| 營運文件 | `docs/official-sources.md` 等 | 移除 Supabase 專屬步驟，保留來源、核准、回滾、健康檢查與主管操作原則 |

## 重寫，不直接移植

| 範圍 | 來源 | 原因 |
| --- | --- | --- |
| 全文搜尋 | `supabase/migrations/*search*` | PGroonga SQL、RPC、RLS 不適用 Pagefind；需求重新以靜態索引與瀏覽器集合運算實作 |
| 版本發布 | PostgreSQL release tables／RPC | 改用不可變 release 目錄、manifest、雜湊與單一 active manifest |
| 備份還原 | `scripts/backup_database.sh`、`restore_database.sh` | 不再備份資料庫；改驗證原始快照、正規化 release 與 Pagefind 索引可重建 |
| 權限模型 | Supabase anonymous／ingest／publisher roles | 靜態網站沒有資料庫登入；改用 GitHub environment、最小權限 token 與人工核准 |

## 不納入新專案

- ChemoDrugStable 的化療調配、安定性、外滲及院內核對內容。
- `chemodrugstable-query` 根目錄首頁及其既有 Git 歷史。
- 舊的 100 份 PDF 排程試行版；PDF 只保留為結構化仿單缺少時的備援設計。
- PostgreSQL／PGroonga／Supabase migration 與帳號建立程式。

## 第三方原作者專案

來源為 `https://github.com/liangRXdev/TFDA-drug-info-search`。使用者表示已獲原作者同意使用；現階段只採用其「獨立藥品網站、靜態快取、PWA 與藥品／健保呈現」概念，未把第三方程式碼直接放入本專案。若日後直接移植，須先保存可修改、公開部署、再散布及署名範圍，並通過 `release_preflight.py`。

## 保護檢查

- 所有移植內容先在新專案測試。
- 來源工作副本與 `chemodrugstable-query` 不接受新專案的反向寫入。
- 未經明確授權，不設定遠端、不推送、不部署、不建立付費資源、不執行正式全量 API。
