import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.fetch_updates import UpdateBatchError, fetch_updates
from tools.pipeline.static_release import active_catalog
from tools.sources import official


ROOT = Path(__file__).resolve().parents[1]
LICENSES = ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw"
UPDATE_XML = ROOT / "tests" / "fixtures" / "structured-51123456.xml"


def seed_initial_state(output: Path, *, no_document: str = "") -> None:
    bundle = official.build_bundle("licenses", LICENSES.read_bytes(), allow_small=True)
    active = active_catalog(bundle)
    output.mkdir(parents=True, exist_ok=True)
    (output / "state.json").write_text(json.dumps({
        "schema_version": 1,
        "catalog_hash": bundle["content_hash"],
        "initial_started_on": "2026-09-01",
        "items": {
            number: {
                "status": "no_document" if number == no_document else "downloaded",
                "checked_at": "2026-09-01T00:00:00+00:00",
            }
            for number in active
        },
    }, ensure_ascii=False), encoding="utf-8")


class StructuredUpdateTests(unittest.TestCase):
    def test_incremental_update_refuses_incomplete_initial_build(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            seed_initial_state(output)
            state_path = output / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            first_number = next(iter(state["items"]))
            state["items"][first_number]["status"] = "failed"
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(UpdateBatchError, "尚有 1 張未完成"):
                fetch_updates(
                    LICENSES,
                    output,
                    start_date=date(2026, 9, 1),
                    through_date=date(2026, 9, 1),
                    request_delay=0,
                    fetch=lambda _query: UPDATE_XML.read_bytes(),
                )

    def test_ten_day_windows_resume_from_last_completed_day(self):
        calls = []

        def fake_fetch(query):
            calls.append((query.normalized().start_date, query.normalized().end_date))
            return UPDATE_XML.read_bytes()

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            seed_initial_state(output)
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
            seed_initial_state(output)
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

    def test_backfill_window_does_not_replace_a_newer_document(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            seed_initial_state(output)
            destination = output / "documents" / "51" / "51123456.json"
            destination.parent.mkdir(parents=True)
            newer = {
                "schema_version": 1,
                "document_count": 1,
                "documents": [{
                    "license_no": "衛部藥製字第123456號",
                    "approved_at": "2099-01-01",
                    "version": "9",
                    "sections": [],
                }],
            }
            destination.write_text(json.dumps(newer, ensure_ascii=False), encoding="utf-8")
            fetch_updates(
                LICENSES,
                output,
                start_date=date(2026, 9, 1),
                through_date=date(2026, 9, 1),
                request_delay=0,
                fetch=lambda _query: UPDATE_XML.read_bytes(),
            )
            saved = json.loads(destination.read_text(encoding="utf-8"))

        self.assertEqual(saved["documents"][0]["version"], "9")

    def test_incremental_document_promotes_previous_no_document_state(self):
        number = "衛部藥製字第123456號"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "structured"
            seed_initial_state(output, no_document=number)
            fetch_updates(
                LICENSES,
                output,
                start_date=date(2026, 9, 1),
                through_date=date(2026, 9, 1),
                request_delay=0,
                fetch=lambda _query: UPDATE_XML.read_bytes(),
            )
            state = json.loads((output / "state.json").read_text(encoding="utf-8"))

        self.assertEqual(state["items"][number]["status"], "downloaded")


if __name__ == "__main__":
    unittest.main()
