# 官方資料與下載邊界

本專案正式資料只接受已列入 `tools/sources/official_sources.json` 的 TFDA 與健保署 HTTPS 網址。重新導向若離開允許網域，下載會立刻失敗。

## 結構化電子仿單

TFDA 於 2025 年 9 月版「藥品電子仿單交換格式」說明：

- 方法為 `GET`，端點是 `https://mcp.fda.gov.tw/Serv/Query.asmx/GetDrugDoc`。
- 可依許可證代碼、健保代碼或更新日期查詢；四個參數至少必填一項。
- 用日期查詢時，開始與結束日期都必填，單次區間不可超過 10 日。
- 回傳 XML 包含藥證、中文／英文品名、藥品類別、版本、核准日期、藥品特性、特殊警語、階層章節、製造廠與藥商；文字或圖片內容可能以 Base64 編碼。
- 文件將此交換格式定位為 Open Data 使用。

官方規格：https://mcp.fda.gov.tw/noticedata/2

這個 API 是資料取得介面，不是全文搜尋 API。它沒有提供「查出所有提到噁心的藥」功能，因此本專案仍需把已取得的章節建立 Pagefind 索引。

官方 PDF 沒有列出每秒或每日請求上限。程式不自行猜測官方允許的流量：預設每 2 秒最多一個請求、每批 100 張，支援續傳；遇到 429 或暫時性錯誤會重試，並遵守伺服器的 `Retry-After`（最長等待 60 秒），重試仍失敗就停止整批。正式大批排程前仍要向 TFDA 確認可接受頻率。

## TFDA 與健保署批次資料

固定來源共九組：

| 資料 | 機關 | 識別碼 |
| --- | --- | --- |
| 未註銷藥品許可證 | TFDA | InfoId 36 |
| 藥品成分 | TFDA | InfoId 43 |
| 仿單 PDF／圖片清冊 | TFDA | InfoId 39 |
| 藥品回收 | TFDA | InfoId 34 |
| 藥品安全資訊 | TFDA | InfoId 53 |
| 風險管理計畫 | TFDA | InfoId 54 |
| 短缺且有替代品 | TFDA | InfoId 104 |
| 短缺且無替代品 | TFDA | InfoId 105 |
| 健保用藥品項 | 健保署 | A21030000I-E41001-001 |

TFDA Open Data API 文件：https://data.fda.gov.tw/swagger-ui/index.html

健保用藥品項資料集：https://data.gov.tw/dataset/23715

健保與 TFDA 藥證資料集明確採政府資料開放授權條款第 1 版。TFDA 網站資料開放宣告也採同一授權，要求使用時註明出處，並排除機關標誌、另有特別聲明或第三方權利的素材。本網站頁尾保留提供機關、資料名稱／版本與授權連結；結構化仿單只發布純文字，不鏡像圖片或 PDF。

TFDA 資料開放宣告：https://www.fda.gov.tw/Tc/opendata.aspx

完整公開發布依據與第三方程式邊界：`docs/publication-rights.md`

## 三段更新流程

1. `official_snapshot.py`：九組批次來源全部下載、格式與最低筆數都通過後，才建立新的不可變 snapshot。
2. `sync_structured.py`／`fetch_structured.py`：初次依有效藥證分批建立結構化仿單庫；每筆都保存狀態，暫時失敗可從原處重試。最後一批先獨立保存，不會緊接著再打一個日期請求。
3. `sync_structured.py`／`fetch_updates.py`：下一輪自動從初次建庫開始日補抓，依官方 10 日上限逐窗取得更新，只追到臺灣上一個完整日；視窗失敗時續傳游標不前進。

資料保存與網站發布前都不只相信 `ready`。系統會重新解析九個 raw 檔，並逐一核對 snapshot 內記錄的官方網址、SHA-256、原始筆數與整理筆數；任何一項不同就停止，不會發布。

逐張建立仿單庫可能需要很多小批次，因此九個批次來源不會每批重抓。第一次建立 `data-state` 或需要新版藥證／健保／安全資料時才選 `refresh_all_nine`；其餘批次用 `reuse_existing`。沿用不代表盲目信任，`validate_official_snapshot.py` 會在任何仿單 API 請求前重新驗證九來源。

增量模式建立後，不再用每 30 天逐張重查舊的 `no_document` 品項阻塞日期更新；若官方日後新增該仿單，日期更新窗會把狀態改為 `downloaded`。每週藥證清單出現的新藥證仍會先逐張補抓。回補舊日期時會保留較新的已存版本，版本號採數字順序比較，不會把版本 10 判成比版本 9 舊。

```sh
# 這兩個命令會連官方服務；正式執行前先確認流量與儲存位置。
python3 tools/pipeline/official_snapshot.py \
  --snapshot-id YYYYMMDD-HHMM \
  --output-root data/official \
  --activate

python3 tools/pipeline/sync_structured.py \
  --license-source data/official/snapshots/YYYYMMDD-HHMM/raw/licenses.raw \
  --output-dir data/structured \
  --max-initial-items 100 \
  --max-update-windows 1 \
  --request-delay 2 \
  --report output/structured-sync.json
```

同一時間只執行一個 `sync_structured.py`，不要讓兩個工作寫入相同 `output-dir`。正式 GitHub workflow 用 concurrency 鎖避免重疊。
