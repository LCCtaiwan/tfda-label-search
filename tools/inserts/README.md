# 電子仿單資料

## 結構化電子仿單 API

`tfda_structured.py` 使用 TFDA 官方 `GetDrugDoc` XML API。它可以依藥證代碼、健保碼或最長 10 天的更新日期區間查詢，保留藥名、版本、核准日期、巢狀章節、原始 HTML、純文字、製造廠及藥商。

圖片的 Base64 本體不寫入搜尋 JSON，只保留檔名及編碼大小，避免樣本無限制膨脹。XML 只有在完整下載、格式驗證及解析成功後才以原子方式取代舊檔；指定藥證或健保碼查不到文件時，也不會清空舊資料。

本機小型驗證：

```sh
python3 tools/inserts/tfda_structured.py \
  --license-code 01016162 \
  --output data/inserts/structured-sample.json

python3 tools/inserts/tfda_structured.py \
  --nhi-code A016162100 \
  --output /tmp/tfda-structured-nhi.json

python3 -m unittest discover -s tests -p 'test_inserts*.py'
```

正式全量更新尚未啟用。API 不提供全文搜尋，後續仍須將已驗證文件匯入自己的搜尋資料庫。

官方規格：https://mcp.fda.gov.tw/noticedata/2

## 本專案目前邊界

- 已納入：TFDA 結構化電子仿單 XML 下載、章節解析、純文字清理與原子寫入。
- 尚未啟用：正式全量或定期下載。
- 不納入第一版：大量掃描 PDF 的 OCR。
- 仿單內容只使用 `GetDrugDoc` 結構化文字；缺少時只連「食藥署仿單頁」`https://mcp.fda.gov.tw/im_detail_1/<URL 編碼的許可證字號>`，不使用 PDF／圖片備援。
