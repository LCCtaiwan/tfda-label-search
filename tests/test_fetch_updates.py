import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.fetch_updates import UpdateBatchError, fetch_updates


ROOT = Path(__file__).resolve().parents[1]
LICENSES = ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw"
UPDATE_XML = ROOT / "tests" / "fixtures" / "structured-51123456.xml"


class StructuredUpdateTests(unittest.TestCase):
    def test_ten_day_windows_resume_from_last_completed_day(self):
        calls = []

        def fake_fetch(query):
            calls.append((query.normalized().start_date, query.normalized().end_date))
            return UPDATE_XML.read_bytes()

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            first = fetch_updates(
                LICENSES,
                output,
                start_date=date(2026, 9, 1),
                through_date=date(2026, 9, 15),
                max_windows=1,
                request_delay=0,
                fetch=fake_fetch,
            )
            second = fetch_updates(
                LICENSES,
                output,
                start_date=None,
                through_date=date(2026, 9, 15),
                max_windows=1,
                request_delay=0,
                fetch=fake_fetch,
            )

        self.assertFalse(first["complete"])
        self.assertTrue(second["complete"])
        self.assertEqual(calls, [
            ("2026/09/01", "2026/09/10"),
            ("2026/09/11", "2026/09/15"),
        ])

    def test_failed_window_keeps_previous_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            with self.assertRaises(UpdateBatchError):
                fetch_updates(
                    LICENSES,
                    output,
                    start_date=date(2026, 9, 1),
                    through_date=date(2026, 9, 10),
                    request_delay=0,
                    fetch=lambda _query: (_ for _ in ()).throw(TimeoutError("temporary")),
                )
            state = json.loads((output / "updates-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["next_date"], "2026-09-01")
        self.assertEqual(state["last_error"]["category"], "TimeoutError")


if __name__ == "__main__":
    unittest.main()
