import base64
import json
from pathlib import Path
import tempfile
import unittest

from tools.inserts.tfda_structured import (
    APIResponseError,
    NoDocumentError,
    Query,
    QueryError,
    build_url,
    parse_xml,
    refresh,
)


WARNING = base64.b64encode("<p>請注意嚴重過敏反應。</p>".encode()).decode()
IMAGE = base64.b64encode(b"fake-image").decode()
SAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<ROOTDOCUMENT>
  <DOCUMENT>
    <INFO>
      <SNO>衛署藥製字第016162號</SNO>
      <CNAME>測試藥品</CNAME>
      <ENAME>TEST DRUG</ENAME>
      <DTYPE>須由醫師處方使用</DTYPE>
      <SNAME></SNAME>
      <VERSION>4</VERSION>
      <VDATE>2026-09-01</VDATE>
    </INFO>
    <CHARACT></CHARACT>
    <WARNING type="text" encode="1">{WARNING}</WARNING>
    <CONTENT>
      <SECTION LEVEL="1" ID="5" border="1" strong="1">
        <NO>5</NO><TITLE>警語及注意事項</TITLE>
        <SECTION LEVEL="2" ID="5.1">
          <NO>5.1</NO><TITLE>懷孕</TITLE>
          <VALUE type="text"><![CDATA[<p>懷孕期間可能發生<strong>噁心</strong>。</p>]]></VALUE>
          <VALUE type="image" encode="1" filenme="警語.jpg">{IMAGE}</VALUE>
          <SECTION LEVEL="3">
            <NO>5.1.1</NO><TITLE>嚴重皮膚不良反應應立即停藥。</TITLE>
          </SECTION>
        </SECTION>
      </SECTION>
    </CONTENT>
    <MAINFACTORY><FACNO>1</FACNO><FACNAME>測試藥廠</FACNAME><FACADD>測試地址</FACADD></MAINFACTORY>
    <COMPANY><COMNO>1</COMNO><COMNAME>測試公司</COMNAME><COMADD>公司地址</COMADD></COMPANY>
  </DOCUMENT>
</ROOTDOCUMENT>""".encode()


class StructuredInsertTests(unittest.TestCase):
    def test_license_and_nhi_build_official_query(self):
        url = build_url(Query(license_code="01016162", nhi_code="A016162100"))
        self.assertTrue(url.startswith("https://mcp.fda.gov.tw/Serv/Query.asmx/GetDrugDoc?"))
        self.assertIn("license=01016162", url)
        self.assertIn("s_code=A016162100", url)

    def test_query_rules_match_official_contract(self):
        for query in (
            Query(),
            Query(start_date="2026-09-01"),
            Query(start_date="2026-09-01", end_date="2026-09-11"),
            Query(license_code="bad"),
        ):
            with self.assertRaises(QueryError):
                query.normalized()
        normalized = Query(start_date="2026-09-01", end_date="2026-09-10").normalized()
        self.assertEqual(normalized.start_date, "2026/09/01")
        self.assertEqual(normalized.end_date, "2026/09/10")

    def test_nested_sections_keep_title_content_and_path(self):
        result = parse_xml(
            SAMPLE,
            Query(license_code="01016162"),
            retrieved_at="2026-09-14T00:00:00+00:00",
        )
        document = result["documents"][0]
        self.assertEqual(document["license_no"], "衛署藥製字第016162號")
        self.assertEqual(document["version"], "4")
        self.assertEqual(document["warning"]["text"], "請注意嚴重過敏反應。")
        self.assertEqual(len(document["sections"]), 3)

        pregnancy = document["sections"][1]
        self.assertEqual(pregnancy["path"], ["警語及注意事項", "懷孕"])
        self.assertIn("噁心", pregnancy["content_text"])
        self.assertNotIn(IMAGE, json.dumps(pregnancy, ensure_ascii=False))
        self.assertEqual(pregnancy["images"][0]["filename"], "警語.jpg")

        level_three = document["sections"][2]
        self.assertIn("嚴重皮膚不良反應", level_three["search_text"])
        self.assertEqual(level_three["parent_id"], "5.1")
        self.assertIn("噁心", document["full_text"])

    def test_official_error_is_not_treated_as_empty_data(self):
        payload = "<Error><Message>請至少輸入一個查詢條件</Message></Error>".encode()
        with self.assertRaisesRegex(APIResponseError, "請至少輸入"):
            parse_xml(payload, Query(license_code="01016162"))

    def test_targeted_empty_result_does_not_replace_previous_file(self):
        empty = b"<ROOTDOCUMENT></ROOTDOCUMENT>"
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.json"
            output.write_text('{"old": true}\n', encoding="utf-8")
            with self.assertRaises(NoDocumentError):
                refresh(Query(license_code="01016162"), output, fetch=lambda query: empty)
            self.assertEqual(output.read_text(encoding="utf-8"), '{"old": true}\n')

    def test_download_failure_does_not_replace_previous_file(self):
        def fail(query):
            raise TimeoutError("temporary failure")

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.json"
            output.write_text('{"old": true}\n', encoding="utf-8")
            with self.assertRaises(TimeoutError):
                refresh(Query(nhi_code="A016162100"), output, fetch=fail)
            self.assertEqual(output.read_text(encoding="utf-8"), '{"old": true}\n')

    def test_successful_refresh_is_atomic_and_searchable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "result.json"
            refresh(
                Query(nhi_code="A016162100"),
                output,
                fetch=lambda query: SAMPLE,
                retrieved_at="2026-09-14T00:00:00+00:00",
            )
            saved = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(saved["document_count"], 1)
        self.assertIn("噁心", saved["documents"][0]["full_text"])


if __name__ == "__main__":
    unittest.main()

