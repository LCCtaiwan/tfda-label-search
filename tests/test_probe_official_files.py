import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from tools.pipeline.probe_official_files import (
    FileProbeAuthorizationError,
    FileProbeError,
    probe_official_files,
)


def write_documents(path: Path, documents: list[dict]) -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "document_count": len(documents),
        "documents": documents,
    }), encoding="utf-8")


class OfficialFileProbeTests(unittest.TestCase):
    def test_no_authorization_makes_zero_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "documents.json"
            write_documents(source, [{
                "license_no": "衛署藥製字第000001號",
                "pdf_urls": ["https://mcp.fda.gov.tw/test/one.pdf"],
            }])
            calls = []
            with self.assertRaisesRegex(FileProbeAuthorizationError, "另行明確授權"):
                probe_official_files(
                    source,
                    root / "report.json",
                    fetcher=lambda url: calls.append(url),
                )
            self.assertEqual(calls, [])
            self.assertFalse((root / "report.json").exists())

    def test_samples_bounded_links_and_classifies_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "documents.json"
            report_path = root / "report.json"
            write_documents(source, [
                {"license_no": "A", "pdf_urls": ["https://mcp.fda.gov.tw/a"]},
                {"license_no": "B", "pdf_urls": ["https://mcp.fda.gov.tw/b"]},
                {"license_no": "C", "pdf_urls": ["https://mcp.fda.gov.tw/c"]},
            ])
            responses = {
                "https://mcp.fda.gov.tw/a": (b"%PDF-1.7 test", "application/pdf", "https://mcp.fda.gov.tw/a"),
                "https://mcp.fda.gov.tw/b": (b"\x89PNG\r\n\x1a\nmore", "image/png", "https://mcp.fda.gov.tw/b"),
            }
            report = probe_official_files(
                source,
                report_path,
                authorized=True,
                max_items=2,
                request_delay=0,
                fetcher=lambda url: responses[url],
            )
            self.assertTrue(report["complete"])
            self.assertEqual(report["available_links"], 3)
            self.assertEqual(report["sampled_links"], 2)
            self.assertEqual(report["summary"]["pdf_header"], 1)
            self.assertEqual(report["summary"]["image_header"], 1)
            self.assertIn("不等於", report["note"])
            self.assertEqual(json.loads(report_path.read_text())["summary"], report["summary"])
            self.assertNotIn("%PDF", report_path.read_text(encoding="utf-8"))

            with self.assertRaisesRegex(FileProbeError, "1 到 100"):
                probe_official_files(
                    source,
                    report_path,
                    authorized=True,
                    max_items=101,
                    request_delay=0,
                    fetcher=lambda _url: self.fail("數量錯誤時不應連線"),
                )

    def test_failure_is_recorded_without_hiding_successes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "documents.json"
            write_documents(source, [
                {"license_no": "A", "pdf_urls": ["https://mcp.fda.gov.tw/a"]},
                {"license_no": "B", "pdf_urls": ["https://mcp.fda.gov.tw/b"]},
            ])

            def fetch(url: str):
                if url.endswith("/b"):
                    raise urllib.error.HTTPError(url, 404, "not found", {}, None)
                return b"<html>viewer</html>", "text/html", url

            report = probe_official_files(
                source,
                root / "report.json",
                authorized=True,
                max_items=2,
                request_delay=0,
                fetcher=fetch,
            )
            self.assertFalse(report["complete"])
            self.assertEqual(report["summary"]["html_page"], 1)
            self.assertEqual(report["summary"]["failed"], 1)
            self.assertEqual(report["results"][1]["error"], "HTTP 404")

    def test_external_source_or_redirect_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "documents.json"
            write_documents(source, [{
                "license_no": "A",
                "pdf_urls": ["https://example.com/a.pdf"],
            }])
            with self.assertRaisesRegex(FileProbeError, "TFDA MCP HTTPS"):
                probe_official_files(source, root / "report.json", authorized=True)

            write_documents(source, [{
                "license_no": "A",
                "pdf_urls": ["https://mcp.fda.gov.tw/a.pdf"],
            }])
            report = probe_official_files(
                source,
                root / "report.json",
                authorized=True,
                request_delay=0,
                fetcher=lambda _url: (b"%PDF-1.7", "application/pdf", "https://evil.example/a.pdf"),
            )
            self.assertFalse(report["complete"])
            self.assertEqual(report["results"][0]["error"], "FileProbeError")


if __name__ == "__main__":
    unittest.main()
