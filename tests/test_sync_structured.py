import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.sync_structured import IncrementalAuthorizationError, sync_structured


ROOT = Path(__file__).resolve().parents[1]
LICENSES = ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw"


def targeted_payload(query):
    return (ROOT / "tests" / "fixtures" / f"structured-{query.license_code}.xml").read_bytes()


class StructuredSyncTests(unittest.TestCase):
    def test_partial_initial_batch_does_not_start_incremental_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            report = sync_structured(
                LICENSES,
                Path(directory) / "structured",
                max_initial_items=1,
                request_delay=0,
                through_date=date(2026, 9, 15),
                fetch_initial=targeted_payload,
                fetch_incremental=lambda _query: self.fail("不應執行增量請求"),
            )
        self.assertEqual(report["phase"], "initial")
        self.assertFalse(report["initial"]["complete"])

    def test_completed_initial_checkpoint_updates_on_the_next_run(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            first = sync_structured(
                LICENSES,
                output,
                max_initial_items=10,
                request_delay=0,
                through_date=date(2099, 1, 1),
                fetch_initial=targeted_payload,
            )
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            through = date.fromisoformat(state["initial_started_on"])
            with self.assertRaisesRegex(IncrementalAuthorizationError, "另行明確授權"):
                sync_structured(
                    LICENSES,
                    output,
                    max_initial_items=10,
                    max_update_windows=1,
                    request_delay=0,
                    through_date=through,
                    fetch_initial=lambda _query: self.fail("完成品不應重抓逐藥證"),
                    fetch_incremental=lambda _query: self.fail("未授權不應執行增量請求"),
                )
            second = sync_structured(
                LICENSES,
                output,
                max_initial_items=10,
                max_update_windows=1,
                allow_incremental=True,
                request_delay=0,
                through_date=through,
                fetch_initial=lambda _query: self.fail("完成品不應重抓逐藥證"),
                fetch_incremental=lambda query: (
                    calls.append((query.normalized().start_date, query.normalized().end_date))
                    or b"<ROOTDOCUMENT></ROOTDOCUMENT>"
                ),
            )

        self.assertEqual(first["phase"], "initial_complete")
        self.assertEqual(second["phase"], "incremental")
        self.assertTrue(second["incremental"]["complete"])
        self.assertEqual(len(calls), 1)

    def test_incremental_phase_does_not_requery_stale_no_document_items(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            sync_structured(
                LICENSES,
                output,
                max_initial_items=10,
                request_delay=0,
                through_date=date(2099, 1, 1),
                fetch_initial=targeted_payload,
            )
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            first_day = date.fromisoformat(state["initial_started_on"])
            sync_structured(
                LICENSES,
                output,
                request_delay=0,
                allow_incremental=True,
                through_date=first_day,
                fetch_initial=lambda _query: self.fail("不應重抓完成品"),
                fetch_incremental=lambda _query: b"<ROOTDOCUMENT></ROOTDOCUMENT>",
            )
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))
            number = next(iter(state["items"]))
            state["items"][number] = {
                "status": "no_document",
                "checked_at": "2020-01-01T00:00:00+00:00",
            }
            (output / "state.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
            report = sync_structured(
                LICENSES,
                output,
                request_delay=0,
                allow_incremental=True,
                through_date=first_day,
                fetch_initial=lambda _query: self.fail("增量期不應逐張重查無仿單"),
                fetch_incremental=lambda _query: self.fail("已追到日期不應再呼叫 API"),
            )

        self.assertEqual(report["phase"], "incremental")
        self.assertEqual(report["initial"]["attempted"], 0)


if __name__ == "__main__":
    unittest.main()
