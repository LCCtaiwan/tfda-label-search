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
            └── data/release.json
```

- `sources/`：九組官方來源的正規化快照、來源網址、擷取時間及內容雜湊。
- `documents.json`：合併目前結構化仿單、成分、健保碼、ATC、安全事件與 TFDA 官方 PDF／圖片備援連結；靜態網站只保存網址，不鏡像檔案。
- `coverage.json`：有效藥證、結構化仿單及只有 metadata 的數量。
- `site/`：可直接交給 GitHub Pages 的完整靜態網站。
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
