import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.static_release import SOURCE_ORDER, StaticReleaseError, active_catalog
from tools.pipeline.state_manifest import (
    build_manifest,
    summarize_incremental,
    summarize_state,
    validate_git_payload,
)
from tools.sources import official


ROOT = Path(__file__).resolve().parents[1]


class StateManifestTests(unittest.TestCase):
    def test_summary_uses_active_licenses_as_denominator(self):
        active = {"A": {}, "B": {}, "C": {}}
        state = {
            "schema_version": 1,
            "items": {
                "A": {"status": "downloaded"},
                "B": {"status": "no_document"},
            },
        }
        summary = summarize_state(state, active, [Path("01/a.json")])
        self.assertEqual(summary["active_licenses"], 3)
        self.assertEqual(summary["checked_licenses"], 2)
        self.assertEqual(summary["downloaded_licenses"], 1)
        self.assertEqual(summary["pending_licenses"], 1)
        self.assertFalse(summary["complete"])

    def test_retired_license_is_reported_but_not_in_current_denominator(self):
        summary = summarize_state(
            {"schema_version": 1, "items": {"OLD": {"status": "downloaded"}}},
            {"A": {}},
            [],
        )
        self.assertEqual(summary["active_licenses"], 1)
        self.assertEqual(summary["retired_state_items"], 1)
        self.assertEqual(summary["pending_licenses"], 1)

    def test_missing_downloaded_file_stops_state_commit(self):
        with self.assertRaises(StaticReleaseError):
            summarize_state(
                {"schema_version": 1, "items": {"A": {"status": "downloaded"}}},
                {"A": {}},
                [],
            )

    def test_build_manifest_validates_a_complete_fixture_state(self):
        license_bundle = official.build_bundle(
            "licenses",
            (ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw").read_bytes(),
            allow_small=True,
        )
        active = active_catalog(license_bundle)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official_dir = root / "official"
            structured_dir = root / "structured"
            (official_dir / "raw").mkdir(parents=True)
            structured_dir.mkdir()
            (official_dir / "manifest.json").write_text(json.dumps({
                "schema_version": 1,
                "snapshot_id": "fixture",
                "created_at": "2026-09-15T00:00:00+00:00",
                "ready": True,
                "sources": {name: {} for name in SOURCE_ORDER},
            }), encoding="utf-8")
            (official_dir / "raw" / "licenses.raw").write_bytes(
                (ROOT / "tests" / "fixtures" / "pipeline_sources" / "licenses.raw").read_bytes()
            )
            (structured_dir / "state.json").write_text(json.dumps({
                "schema_version": 1,
                "catalog_hash": license_bundle["content_hash"],
                "items": {number: {"status": "no_document"} for number in active},
            }, ensure_ascii=False), encoding="utf-8")

            manifest = build_manifest(
                official_dir, structured_dir, allow_small_fixtures=True
            )
            with self.assertRaisesRegex(StaticReleaseError, "增量更新游標"):
                build_manifest(
                    official_dir,
                    structured_dir,
                    allow_small_fixtures=True,
                    require_incremental=True,
                )
            (structured_dir / "updates-state.json").write_text(json.dumps({
                "schema_version": 1,
                "catalog_hash": license_bundle["content_hash"],
                "next_date": "2020-01-01",
            }), encoding="utf-8")
            with self.assertRaisesRegex(StaticReleaseError, "超過 14 天門檻"):
                build_manifest(
                    official_dir,
                    structured_dir,
                    allow_small_fixtures=True,
                    require_incremental=True,
                    max_incremental_lag_days=14,
                )

        self.assertTrue(manifest["complete"])
        self.assertEqual(manifest["checked_licenses"], len(active))
        self.assertGreater(manifest["file_count"], 0)
        self.assertGreater(manifest["total_bytes"], 0)
        self.assertEqual(len(manifest["data_sha256"]), 64)

    def test_git_payload_limit_fails_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            oversized = root / "too-large.raw"
            oversized.write_bytes(b"1234")
            with self.assertRaises(StaticReleaseError):
                validate_git_payload([oversized], root, max_bytes=3)

    def test_incremental_state_reports_lag_and_rejects_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "updates-state.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "catalog_hash": "catalog",
                "next_date": "2020-01-01",
            }), encoding="utf-8")
            summary = summarize_incremental(path, "catalog")
            self.assertTrue(summary["incremental_initialized"])
            self.assertGreater(summary["incremental_lag_days"], 0)

            state = json.loads(path.read_text(encoding="utf-8"))
            state["last_error"] = {"message": "temporary"}
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(StaticReleaseError):
                summarize_incremental(path, "catalog")


if __name__ == "__main__":
    unittest.main()
