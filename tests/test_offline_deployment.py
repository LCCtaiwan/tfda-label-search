import json
from argparse import Namespace
from datetime import date
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.pipeline.approval_summary import build_approval_summary
from tools.pipeline.official_snapshot import build_snapshot
from tools.pipeline.release_preflight import run_preflight
from tools.pipeline.sync_structured import sync_structured
from tools.pipeline.state_manifest import build_manifest
from tools.pipeline.static_release import SOURCE_ORDER, build_release
from tools.sources import official


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class OfflineDeploymentTests(unittest.TestCase):
    def test_data_state_to_validated_pages_candidate(self):
        specs = official.load_sources()
        source_dir = FIXTURES / "pipeline_sources"
        payloads = {
            specs[name]["url"]: (source_dir / f"{name}.raw").read_bytes()
            for name in SOURCE_ORDER
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_root = root / "snapshot-root"
            build_snapshot(
                snapshot_root,
                "offline-v1",
                activate=True,
                download=lambda url: payloads[url],
                allow_small_fixtures=True,
            )
            official_current = root / "state" / "official" / "current"
            snapshot = snapshot_root / "snapshots" / "offline-v1"
            shutil.copytree(snapshot / "raw", official_current / "raw")
            shutil.copy2(snapshot / "manifest.json", official_current / "manifest.json")

            structured = root / "state" / "structured"
            report = sync_structured(
                official_current / "raw" / "licenses.raw",
                structured,
                max_initial_items=100,
                request_delay=0,
                through_date=date(2099, 1, 1),
                fetch_initial=lambda query: (
                    FIXTURES / f"structured-{query.license_code}.xml"
                ).read_bytes(),
            )
            self.assertEqual(report["phase"], "initial_complete")
            initial_state = json.loads(
                (structured / "state.json").read_text(encoding="utf-8")
            )
            sync = sync_structured(
                official_current / "raw" / "licenses.raw",
                structured,
                max_initial_items=100,
                allow_incremental=True,
                request_delay=0,
                through_date=date.fromisoformat(initial_state["initial_started_on"]),
                fetch_initial=lambda _query: self.fail("完成後不應重抓逐藥證"),
                fetch_incremental=lambda _query: b"<ROOTDOCUMENT></ROOTDOCUMENT>",
            )
            self.assertEqual(sync["phase"], "incremental")
            state_manifest = build_manifest(
                official_current,
                structured,
                allow_small_fixtures=True,
                require_incremental=True,
                max_incremental_lag_days=0,
            )
            self.assertTrue(state_manifest["complete"])
            self.assertEqual(state_manifest["structured_coverage"], 1)
            self.assertEqual(state_manifest["incremental_lag_days"], 0)
            self.assertFalse((official_current / "normalized").exists())

            release_root = root / "candidate"
            release = build_release(Namespace(
                release_id="offline-v1",
                release_root=release_root,
                source_dir=official_current / "raw",
                source_manifest=official_current / "manifest.json",
                structured=sorted((structured / "documents").rglob("*.json")),
                min_structured_coverage=1.0,
                app_revision="a" * 40,
                data_revision="b" * 40,
                allow_small_fixtures=True,
                activate=False,
            ))
            release_dir = release_root / "releases" / "offline-v1"
            site = release_dir / "site"
            catalog = json.loads((site / "data" / "catalog.json").read_text(encoding="utf-8"))
            preflight = run_preflight(
                ROOT / "config" / "publication-policy.json", site, ROOT
            )
            state_report = root / "verified-data-state.json"
            preflight_report = root / "publication-preflight.json"
            state_report.write_text(json.dumps(state_manifest), encoding="utf-8")
            preflight_report.write_text(json.dumps(preflight), encoding="utf-8")
            approval_summary = build_approval_summary(
                release_dir / "manifest.json",
                release_dir / "coverage.json",
                state_report,
                preflight_report,
                site / "data" / "synonyms.json",
                min_structured_coverage=1.0,
                max_lag_days=0,
            )

        self.assertTrue(release["ready"])
        self.assertTrue(preflight["ready"])
        self.assertEqual(release["coverage"]["structured_coverage"], 1)
        self.assertEqual(catalog["document_count"], 2)
        self.assertIn("2（100.00%", approval_summary)
        self.assertIn("目前沒有正式核准的人工同義詞", approval_summary)
        self.assertFalse((release_root / "active.json").exists())


if __name__ == "__main__":
    unittest.main()
