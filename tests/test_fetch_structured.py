import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.fetch_structured import StructuredBatchError, fetch_batch


ROOT = Path(__file__).resolve().parents[1]


class StructuredBatchTests(unittest.TestCase):
    def payload(self, code: str) -> bytes:
        return (ROOT / "tests" / "fixtures" / f"structured-{code}.xml").read_bytes()

    def test_batch_resumes_without_downloading_completed_license_again(self):
        calls = []

        def fake_fetch(query):
            calls.append(query.license_code)
            return self.payload(query.license_code)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            first = fetch_batch(
                ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw",
                output,
                max_items=1,
                request_delay=0,
                fetch=fake_fetch,
            )
            second = fetch_batch(
                ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw",
                output,
                max_items=10,
                request_delay=0,
                fetch=fake_fetch,
            )
            files = sorted((output / "documents").rglob("*.json"))

        self.assertEqual(first["downloaded"], 1)
        self.assertEqual(first["remaining"], 1)
        self.assertTrue(second["complete"])
        self.assertEqual(calls, ["01016162", "51123456"])
        self.assertEqual(len(files), 2)
        self.assertEqual({path.parent.name for path in files}, {"01", "51"})
        self.assertRegex(second["initial_started_on"], r"^\d{4}-\d{2}-\d{2}$")

    def test_failure_is_saved_and_retried_on_next_run(self):
        attempts = 0

        def flaky(query):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("temporary")
            return self.payload(query.license_code)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            source = ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw"
            with self.assertRaises(StructuredBatchError):
                fetch_batch(source, output, max_items=1, request_delay=0, fetch=flaky)
            failed = json.loads((output / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["items"]["衛署藥製字第016162號"]["status"], "failed")
            report = fetch_batch(source, output, max_items=1, request_delay=0, fetch=flaky)

        self.assertEqual(report["downloaded"], 1)
        self.assertEqual(attempts, 2)

    def test_targeted_empty_response_is_a_completed_no_document_result(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            source = ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw"
            report = fetch_batch(
                source,
                output,
                max_items=1,
                request_delay=0,
                fetch=lambda _query: b"<ROOTDOCUMENT></ROOTDOCUMENT>",
            )
            self.assertEqual(report["no_document"], 1)
            self.assertEqual(report["remaining"], 1)

            state_path = output / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["items"]["衛署藥製字第016162號"]["checked_at"] = "2020-01-01T00:00:00+00:00"
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            retried = fetch_batch(
                source,
                output,
                max_items=1,
                request_delay=0,
                fetch=lambda query: self.payload(query.license_code),
            )
            self.assertEqual(retried["downloaded"], 1)

    def test_stale_no_document_items_remain_pending_until_each_is_rechecked(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            source = ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw"
            fetch_batch(
                source,
                output,
                max_items=10,
                request_delay=0,
                fetch=lambda _query: b"<ROOTDOCUMENT></ROOTDOCUMENT>",
            )
            state_path = output / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            for item in state["items"].values():
                item["checked_at"] = "2020-01-01T00:00:00+00:00"
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            report = fetch_batch(
                source,
                output,
                max_items=1,
                request_delay=0,
                fetch=lambda _query: b"<ROOTDOCUMENT></ROOTDOCUMENT>",
            )

        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["remaining"], 1)
        self.assertFalse(report["complete"])


if __name__ == "__main__":
    unittest.main()
