# 官方仿單檔案抽查

TFDA 的「仿單圖檔連結」可能指向 PDF、圖片、檢視網頁或其他內容。只看網址副檔名不能證明檔案格式，更不能證明整份 PDF 可正常開啟。

`tools/pipeline/probe_official_files.py` 會依 release 的 `documents.json`，按固定順序抽查最多 1–100 個官方連結。它只允許 `https://mcp.fda.gov.tw`，每個連結最多讀取前 64 KiB，不保存 PDF 或圖片內容。報告會分成：

- `pdf_header`：內容以 PDF 檔頭開始。
- `image_header`：辨識到 PNG、JPEG、GIF、TIFF 或 WebP 檔頭。
- `html_page`：回應是 HTML 檢視頁。
- `unknown`：有回應，但檔頭無法判斷。
- `failed`：HTTP、連線、空回應或安全檢查失敗。

這是小量品質抽查，不是全文下載器。`pdf_header` 也不代表已驗證整份 PDF 完整、可讀或含可搜尋文字。

## 執行方式

必須先取得「本輪抽查官方檔案連結」的明確授權，再執行：

```bash
python3 tools/pipeline/probe_official_files.py \
  --documents <release資料夾>/documents.json \
  --report <輸出位置>/official-file-probe.json \
  --max-items 25 \
  --authorization authorized
```

未傳入 `--authorization authorized` 時，只要有待抽查連結就會在零次連線時停止。報告有任何 `failed` 時，命令以非零狀態結束，但已完成與失敗的逐筆結果都會保留，供人工核對。

正式全量分類仍需另做獲准的完整檔案驗證；本工具不能把抽查結果外推為全部仿單都可讀。
