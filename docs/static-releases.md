# 靜態版本與失敗保護

每次更新先在新的暫存資料夾完成，不會直接改掉目前可用的版本。只有九組官方來源格式、有效藥證分母、結構化仿單內容完整性與 Pagefind 建置全部通過，才會產生 `ready: true` 的不可變 release。

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

- `sources/`：八組會用於發布的官方來源正規化快照、來源網址、擷取時間及內容雜湊。InfoId 39 仍在 data-state 的九來源 snapshot 驗證與來源雜湊中，但不輸出 `sources/pdf_catalog.json`。
- `documents.json`：合併目前結構化仿單、成分、健保碼、ATC、健保支付價／有效期間／規格／給付章節、其他官方事件的日期／標題／狀態／來源，以及由藥證字號產生的食藥署仿單頁入口；不含 `pdf_urls` 或官方仿單檔案連結，仿單內容只來自 `GetDrugDoc`。健保與其他官方事件都只表示資料版本日期以前的紀錄，不是目前狀態保證。
- release 根目錄的 `coverage.json`：有效藥證、`structured_licenses`（有結構化仿單文字）、`metadata_only_licenses`（尚無結構化仿單）、結構化涵蓋率及健保連接結果。
- `site/`：可直接交給 GitHub Pages 的完整靜態網站。
- `site/data/coverage.json`：供網站顯示的精簡涵蓋報告；只分 `searchable_text_documents`（有結構化仿單文字）與 `metadata_only_documents`（尚無結構化仿單，連食藥署仿單頁）。
- `site/data/release.json`：公開版本身分證，保存 release ID、程式完整 Git SHA、資料完整 Git SHA、官方 snapshot、真實資料擷取時間、來源雜湊與涵蓋率。
- 網頁只以 `data_retrieved_at` 判定官方資料日期，不以 `built_at` 代替；每次開啟都依臺灣日期計算，超過 14 天或日期不可信時警告。
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

正式流程不可使用 `--allow-small-fixtures`，而且必須提供兩個完整 40 碼 Git SHA 與 `--source-manifest`。程式會重新核對九個 raw 檔與 snapshot manifest；C-029 起預設不設涵蓋率下限，保留涵蓋報告並明示逐步補齊；其他完整性關卡照常檢查。`--min-structured-coverage` 僅保留作離線試驗的可選限制，正式 workflow 不設定。尚無結構化文字的有效藥證會保留一張明確標示的資料卡與官方入口，但不能冒充全文可搜尋仿單。

正式 Pages workflow 另傳入 `--max-official-snapshot-age-days 14`。release manifest 會保存 `official_snapshot_age_days`；超過門檻或快照日期不可信時，候選版在產生前停止。

2026-11-24 起，官方檔案連結、PDF 備援與檔頭抽查不參與發布內容或涵蓋分類。舊的 `probe_official_files.py` 與其離線測試保留，供歷史證據查閱；不由 workflow 或 release 建置呼叫。新 release 沒有 `pdf_urls`，不能再依舊文件從新 release 抽查檔案。九來源來源雜湊仍保留 `pdf_catalog` 鍵作 snapshot 稽核識別，並非檔案連結。

初次建庫未完成且無增量游標時，Pages 預檢用 `--allow-initial-building` 允許發布；已有游標仍強制 14 天，建庫完成卻缺游標不允許。首次與程式 SHA 改變需 reviewer，同已核准程式的成功排程資料更新可自動發布，見 `deployment.md`。
