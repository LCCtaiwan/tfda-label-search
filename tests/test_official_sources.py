import json
import io
from pathlib import Path
import unittest
import urllib.error
from unittest import mock

from tools.sources import official
from tools.sources.official import SourceError, build_bundle, checked_url, decode_rows, extract_licenses, parse_date


class FakeResponse(io.BytesIO):
    def geturl(self):
        return "https://data.fda.gov.tw/data/opendata/export/34/json"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

class OfficialSourceTests(unittest.TestCase):
    def test_only_known_official_download_hosts_are_allowed(self):
        self.assertEqual(checked_url("https://data.fda.gov.tw/data/opendata/export/34/json"), "https://data.fda.gov.tw/data/opendata/export/34/json")
        for url in ("http://data.fda.gov.tw/a", "https://evil.example/a", "https://data.fda.gov.tw.evil.example/a"):
            with self.assertRaises(SourceError): checked_url(url)

    def test_roc_and_gregorian_dates_are_normalized(self):
        self.assertEqual(parse_date("115.09.14"), "2026-09-14")
        self.assertEqual(parse_date("2026-09-14"), "2026-09-14")
        self.assertEqual(parse_date("沒有日期"), "")

    def test_ingredients_are_traceable_and_positioned_per_license(self):
        rows = [{"許可證字號":"衛署藥製字第016162號","處方標示":"EACH TABLET CONTAINS:","成分名稱":"TEST A","成分代碼":"A","含量描述":"10 MG","含量":"10","含量單位":"MG"},
                {"許可證字號":"衛署藥製字第016162號","處方標示":"","成分名稱":"TEST B","成分代碼":"B","含量描述":"5 MG","含量":"5","含量單位":"MG"}]
        bundle = build_bundle("ingredients", json.dumps(rows, ensure_ascii=False).encode(), allow_small=True, retrieved_at="2026-09-14T00:00:00Z")
        self.assertEqual(bundle["kind"], "ingredients"); self.assertEqual([r["position"] for r in bundle["records"]], [1, 2])
        self.assertEqual(bundle["records"][0]["source_record"]["成分名稱"], "TEST A")

    def test_safety_alert_extracts_only_complete_license_numbers(self):
        licenses = extract_licenses("品名（衛署藥製字第016162號）；另列藥輸025224")
        self.assertEqual(licenses[0]["license_no"], "衛署藥製字第016162號")
        self.assertNotIn("藥輸025224", [item["license_no"] for item in licenses])

    def test_no_data_shortage_sentinel_is_not_an_event(self):
        rows = [{"編號":"沒有資料","公告更新時間":None,"中文品名":None,"許可證字號":None,"供應狀態":None}]
        bundle = build_bundle("shortage_without_alternative", json.dumps(rows, ensure_ascii=False).encode(), allow_small=True)
        self.assertEqual(bundle["source_record_count"], 1); self.assertEqual(bundle["normalized_record_count"], 0)

    def test_missing_official_fields_stop_the_update(self):
        with self.assertRaises(SourceError):
            build_bundle("recalls", '[{"文號":"x"}]'.encode(), allow_small=True)

    def test_download_retries_a_temporary_connection_failure(self):
        opener = mock.Mock()
        opener.open.side_effect = [
            urllib.error.URLError("temporary"),
            FakeResponse(b'[{"ok":true}]'),
        ]
        with mock.patch.object(official.urllib.request, "build_opener", return_value=opener), \
             mock.patch.object(official.time, "sleep") as sleep:
            result = official.download(
                "https://data.fda.gov.tw/data/opendata/export/34/json",
                attempts=2,
            )
        self.assertEqual(result, b'[{"ok":true}]')
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_download_does_not_retry_a_client_error(self):
        opener = mock.Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            "https://data.fda.gov.tw/missing", 404, "missing", {}, None
        )
        with mock.patch.object(official.urllib.request, "build_opener", return_value=opener), \
             mock.patch.object(official.time, "sleep") as sleep:
            with self.assertRaises(SourceError):
                official.download("https://data.fda.gov.tw/missing")
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()

if __name__ == "__main__": unittest.main()

