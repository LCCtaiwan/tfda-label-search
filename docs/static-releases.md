# 靜態版本與失敗保護

每次更新先在新的暫存資料夾完成，不會直接改掉目前可用的版本。只有九組官方來源格式、有效藥證分母、結構化仿單涵蓋率與 Pagefind 建置全部通過，才會產生 `ready: true` 的不可變 release。

## 目錄

```text
release-root/
├── active.json
└── releases/
    └── <release-id>/
        ├── manifest.json
        ├── coverage.json
        ├── documents.json
        ├── sources/
        └── site/
            └── data/
                ├── coverage.json
                └── release.json
```

- `sources/`：九組官方來源的正規化快照、來源網址、擷取時間及內容雜湊。
- `documents.json`：合併目前結構化仿單、成分、健保碼、ATC、健保支付價／有效期間／規格／給付章節、其他官方事件的日期／標題／狀態／來源，以及 TFDA 官方 PDF／圖片備援連結；靜態網站只保存網址，不鏡像檔案。健保與其他官方事件都只表示資料版本日期以前的紀錄，不是目前狀態保證。
- release 根目錄的 `coverage.json`：有效藥證、結構化仿單、metadata-only 有／無官方檔案、具有官方檔案的藥證數、連結總數及健保連接結果。
- `site/`：可直接交給 GitHub Pages 的完整靜態網站。
- `site/data/coverage.json`：供網站顯示的精簡涵蓋報告；每張資料分成有可搜尋文字、只有官方檔案連結、兩者都沒有。
- `site/data/release.json`：公開版本身分證，保存 release ID、程式完整 Git SHA、資料完整 Git SHA、官方 snapshot、真實資料擷取時間、來源雜湊與涵蓋率。
- `active.json`：目前核准版本的指標。候選版本失敗時不會改動。

已完成的 release 不可用相同 ID 覆寫。要回復舊版，只需在人工確認後把 `active.json` 指回已驗證的舊 release；不要修改舊 release 內容。

## 小型本機驗證

以下命令只使用測試資料，不連官方 API：

```sh
python3 tools/pipeline/static_release.py \
  --release-id local-fixture-v1 \
  --release-root output/releases \
  --source-dir tests/fixtures/pipeline_sources \
  --structured tests/fixtures/structured-real-sample.json \
  --app-revision aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --data-revision bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
  --min-structured-coverage 0.5 \
  --allow-small-fixtures \
  --activate
```

正式流程不可使用 `--allow-small-fixtures`，而且必須提供兩個完整 40 碼 Git SHA 與 `--source-manifest`。程式會重新核對九個 raw 檔與 snapshot manifest；預設結構化文字涵蓋率門檻為 98%。尚無結構化文字的有效藥證會保留一張明確標示的資料卡與官方入口，但不能冒充全文可搜尋仿單。

官方清冊欄位名稱雖包含「圖檔」，網址本身不足以可靠分辨可讀 PDF、單張圖片或其他官方呈現形式。因此第一版只報告「有官方檔案連結」；需在獲准的小批正式資料中檢查實際回應後，才能增加更細的檔案類型分類。
