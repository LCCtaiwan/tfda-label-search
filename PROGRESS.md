# 進度

## 目前停點：C-030（2026-11-25，workflow 有效性修正）

- 在 `air/structured-only` 修正 refresh 的 job-level env 使用不允許的 `runner.temp`：第一步改用 runner 環境變數，將 `APP_COPY`、`SNAPSHOT_ROOT`、`SNAPSHOT_ID` 寫入 `GITHUB_ENV`，後續引用不變。
- 三份 workflow 已離線審查 context 位置與事件分支，deploy-pages／ci 無須修改。新增初始化實際執行與 job-level context 回歸測試。
- 工具檢查：Python 85／85、Node 12／12；三份 YAML 解析及 35 個 shell block 的 `bash -n` 通過。未安裝 actionlint，未做 GitHub 線上驗收；未連網、切分支、commit 或 push。下一步是在允許的環境重新執行 GitHub workflow，確認平台接受。

## 目前停點：C-029（2026-11-25，目標 9–12）

- 機器：air；分支：`air/structured-only`。保留使用者既有目標文件差異；未切分支、commit、push、部署或呼叫網路，由 Claude 審查及提交。
- 已實作每日臺灣 10:23 排程、5／500 張選項、雙 TFDA 授權鎖、snapshot 缺少／超過 14 天自動更新；手動授權與增量另行授權、2 秒間隔、Retry-After 及續傳保留。
- 可選 Secret `FORMULARY_CSV_URL` 只在記憶體排序院內優先（ATC＋英文名稱／成分 → ATC → 其他）；停用列忽略、同層穩定、只記合計，失敗照原順序。
- 正式發布取消 98% 下限，保留完整性與新鮮度檢查。依使用者本輪澄清：初次建庫未完成且尚無增量游標可先上線；已有游標仍須不超過 14 天，完成卻缺游標仍拒絕。網頁顯示逐步補齊數量、百分比與最後更新日；`coverage.json` 保留，空文字不灌水。
- 首次、程式 SHA 改變及手動發布走 `github-pages` reviewer；相同最後核准 app SHA 的成功排程資料更新才可走 `github-pages-auto`。人工部署及 smoke 成功後才寫入 `data-state/approved-app.json`；排程 artifact 固定 upstream run 與 app/data SHA。
- 操作文件已列出四個 repository variables、可選 secret、兩個 environment、本人核准與停機步驟。見 `docs/deployment.md`、`docs/supervisor-guide.md`。
- 工具檢查：Python 83／83、Node 12／12、三份 YAML／34 個 shell block、同義詞與差異檢查通過，證據見本輪 `docs/develog.md` C-029。尚無 GitHub、API、reviewer、正式 Pages 或 Chromium 視覺／互動驗收；本輪只使用 fixture、mock 與本機檔案。

## 目前狀態

- 專案名稱：「TFDA仿單搜尋」。
- 本地位置：`/Users/lcc/Desktop/PGY許願池/tfda-label-search`。
- `SPEC.md` 已由使用者確認。
- 已決定與 `chemodrugstable-query` 分開，既有線上網站與 Git 歷史保持不變。
- 已移植 TFDA 結構化仿單解析器、九個官方來源設定、來源驗證器及 15 個 Python 測試。
- 已建立 Pagefind 靜態索引產生器與查詢頁，支援中文／英文、AND、OR、NOT、章節原文及官方連結。
- 已建立不可變靜態 release：串接藥證、成分、健保碼、ATC、安全事件及食藥署仿單頁；候選版失敗不會切換 `active.json`。
- 已核對 TFDA 2025 年 9 月官方電子仿單交換格式，並建立九來源全成全敗 snapshot、逐藥證續傳與 10 日增量更新工具。
- 搜尋索引已改成每份仿單一筆候選記錄，命中後逐章精確比對；結果可每次載入 50 筆。
- 1,000 與 5,000 份合成容量試驗通過；加入精確藥品目錄後，5,000 份、250,000 章網站約 103 MB，36.14 秒建好，瀏覽器首次搜尋約 1.1 秒。
- CI 已加入 10 個 Chromium 端到端測試，涵蓋任意短詞、英文、AND／OR／NOT、測試專用 reviewed 同義詞、分批載入、完整藥證、網址深連結、輸入上限、去重、metadata-only 食藥署仿單頁、歷史官方事件、健保詳細資料、資料過期警告、可見署名與手機寬度。
- 已完成受授權的手動／排程資料更新與 Pages 發布 workflow：`data-state` 每批成功才 commit；發布預設上鎖，必須先設定主管 required reviewer。
- 結構化仿單依證別分片保存，避免單一資料夾累積過多檔案；429／暫時錯誤會遵守最長 60 秒的 `Retry-After`。
- 已完成完整離線發布演練、英文搜尋與頁尾資料版本／SHA-256 指紋；目前 76 個 Python／Node（64 Python + 12 Node）與 10 個 Chromium 測試通過。
- 5000 份手機資源量測：常見詞新增約 8.38 MiB JS heap、傳輸 4.33 MiB；完整藥證新增約 6.61 MiB、傳輸 3.62 MiB。
- `data-state` 只保留官方 raw、manifest、結構化仿單與人工部署核准紀錄；單檔超過 95 MiB 會在 commit 前停止，manifest 會留下總容量與最大檔案供稽核。
- 2026-09-16 已依授權下載九項正式官方資料；最大檔是 96,434,108 bytes 的健保資料，低於 95 MiB 保護線，但只剩約 3.0 MiB 空間。
- 已核對 TFDA、健保署與政府資料開放授權：正式網站只發布結構化仿單純文字，排除內嵌圖片、PDF 鏡像及機關標誌，並補齊提供機關與授權署名。
- `release_preflight.py` 會產生公開發布稽核報告，授權依據超過一年會要求重查；`TFDA_API_CALLS_AUTHORIZED` 與 `PUBLICATION_AUTHORIZED` 兩道變數鎖預設都不放行。
- 每個網站都有程式／資料完整 SHA 的 `release.json`；部署 workflow 可指定舊 SHA 走同一條主管核准流程回滾，完成後會用 Chromium 在正式網址核對版本並搜尋一張目錄內藥證。
- 正式資料 workflow 已接入初次建庫與 10 日窗增量協調器：最後一批初始資料先獨立 commit，下一輪從建庫開始日補更新；發布時已有增量游標不得落後超過 14 天；初次未完成可暫無游標，完成後必須補上。
- 正式發布會重新解析九個 raw 檔並核對 snapshot 的網址、SHA-256 與筆數；每張 downloaded 仿單也會核對分片路徑、藥證與狀態，無關 JSON 不可混入。
- 公開的資料日期使用 snapshot 實際擷取時間；部署 smoke 會核對本次核准的完整 app/data SHA，回滾時也使用該舊 app SHA 的檢查器。
- GitHub 官方 Actions 已依 2026-09-15 官方 release 查詢結果更新，並固定到完整 commit SHA。
- `npm audit --audit-level=high --package-lock-only` 回報 0 個已知漏洞。
- 資料 workflow 手動預設每次最多 25 張並要求本輪授權勾選，排程固定 500 張且另需排程授權；九個批次來源平常重用已驗證 snapshot，第一次或主動更新時才全部重抓。
- 沿用 snapshot 時會在結構化仿單 API 呼叫前先重驗九來源；不可信資料會在零次仿單請求時停止。
- metadata-only 結果只顯示指定 `im_detail_1/` 路徑的「食藥署仿單頁」；舊 PDF 備援連結已移除。
- 公開涵蓋摘要與 `data/coverage.json` 只計算有／無結構化仿單文字。
- 部署 smoke 會交叉核對核准 release、公開涵蓋報告及藥品目錄；本機完整演練已確認 114 份總數與涵蓋分類一致（C-028 起改為兩類）。
- 正式人工同義詞現在必須通過格式、字數、正規化重複、跨組衝突、審查人與日期驗證；未審查草稿不會公開，部署附件會保留實際公開詞表供主管查看。
- 完成 `q`／`any`／`exclude` 深連結、自動搜尋與網址同步；相容 `all`／`not` 舊參數並限制最多 10 詞、每詞 2–80 字元，ChemoDrugStable 本身未修改。
- 部署後 smoke 會直接用正式網址的 `?q=<完整藥證>` 驗證 GitHub Pages 子路徑與自動搜尋，不再只靠手動填表測試。
- 回收、安全警示、風險管理及短缺資料以折疊的歷史官方關聯顯示，不加入仿單全文命中；來源、類型與日期不合規時建置失敗。
- 公開發布政策固定九個已審查官方資料集，清單少一個或多一個都不放行。
- 健保品項會保留規格、劑型、支付價、有效期間、藥商、給付章節與官方連結；畫面明示這不是目前給付或價格保證，外站網址與錯誤日期會停止建置。
- 網站每天以臺灣日期重算官方資料年齡；超過 14 天、日期缺少或在未來時會醒目警告，且不以較新的建置日期冒充資料日期。
- Pages 發布會在 `data-state` 預檢與 release 建置兩層拒絕超過 14 天的九來源 snapshot，稽核報告會留下實際年齡。
- 資料更新 workflow 也會在任何仿單 API 前檢查 snapshot 年齡；手動超過 14 天以零次仿單請求停止，要求改用 `refresh_all_nine`；排程自動更新缺少或過期 snapshot。
- 初次逐藥證與日期增量使用兩個授權邊界：張數只管初次建庫；日期窗可能回傳更多文件，手動須另外勾選增量授權，排程以 `TFDA_SCHEDULE_AUTHORIZED=true` 授權。
- 保留但不接入發布的歷史官方檔案抽查器（需逐次授權）：最多 100 個、每個只讀 64 KiB 檔頭、不保存內容，分辨 PDF／圖片／HTML／未知與失敗，外站及外站轉址會拒絕。
- Pages 候選版會在主管核准前產生一頁白話摘要，交叉核對 release、data-state、涵蓋率、發布權利及同義詞五份證據；任何數字、snapshot 或 commit 不一致時停止。
- 2026-09-16 已精確執行 25 次逐藥證 API：7 份有結構化仿單、18 筆無文件、0 失敗；未使用重試，沒有呼叫日期增量或官方檔案抽查。
- 真實小批發現並修正跨章節 AND／NOT、917 字短缺狀態上限及健保碼摘要重複；本機 22,494 張藥證網站約 295 MiB，Pagefind 約 94 MiB。
- 尚未建立遠端、推送、部署、建立雲端資源或大量呼叫官方 API。

## 目前目標

完成獨立、可正式上線且可交接的 TFDA 仿單搜尋成品；第一個功能里程碑是證明 Pagefind 能處理繁體中文醫療短詞、仿單章節結果及合理的全量容量。

## 下一步

1. Claude 審查 C-029 與既有目標文件差異，重跑離線測試及允許本機伺服器環境的 11 項 Chromium；通過後由 Claude commit／GitHub 操作，本輪 Codex 不執行。
2. 依 `docs/deployment.md` 設 Pages、四個 repository variables、可選 `FORMULARY_CSV_URL` 及兩個 environment；五張手動試跑時排程 variable 保持 false。
3. Claude 執行 5 張 → 授權後 500 張，檢查來源、涵蓋、資料 commit；手動首次發布由使用者本人按 Approve and deploy，確認 smoke 及核准紀錄 commit 成功。
4. 正式授權日更後才同時開啟兩個 TFDA 變數；驗證臺灣 10:23 排程及同程式 SHA 的自動發布。向 TFDA 確認正式頻率，累積代表性真實資料後重做容量／品質驗收。
5. 持續監控健保原始檔 95 MiB 保護線與九來源／增量 14 天限制；超限先停下評估儲存方式，不繞過檢查。

## 尚待確認

- TFDA 正式批次呼叫頻率。
- 全量結構化仿單涵蓋率與 Pagefind 索引大小。
- 若日後要加入 PDF、圖片、機關標誌或另有特別聲明的素材，須重新確認公開使用權利。
- 若日後直接複製 `TFDA-drug-info-search` 程式碼，須保存原作者同意的修改、公開部署、再散布及署名範圍；目前沒有複製第三方程式。
- GitHub environment reviewer 與自動 Pages 的實際設定及驗收；目前指定使用者本人 `LCCtaiwan` 核准。
