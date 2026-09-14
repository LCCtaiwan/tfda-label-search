import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.official_snapshot import build_snapshot
from tools.pipeline.static_release import SOURCE_ORDER, StaticReleaseError
from tools.pipeline.validate_official_snapshot import validate_snapshot
from tools.sources import official


ROOT = Path(__file__).resolve().parents[1]


class ValidateOfficialSnapshotTests(unittest.TestCase):
    def test_existing_snapshot_is_revalidated_before_reuse(self):
        specs = official.load_sources()
        fixtures = ROOT / "tests" / "fixtures" / "pipeline_sources"
        payloads = {
            specs[name]["url"]: (fixtures / f"{name}.raw").read_bytes()
            for name in SOURCE_ORDER
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot_root = Path(directory)
            build_snapshot(
                snapshot_root,
                "reuse-v1",
                download=lambda url: payloads[url],
                allow_small_fixtures=True,
            )
            snapshot = snapshot_root / "snapshots" / "reuse-v1"
            report = validate_snapshot(
                snapshot / "raw",
                snapshot / "manifest.json",
                allow_small_fixtures=True,
            )
            self.assertTrue(report["ready"])
            self.assertEqual(set(report["sources"]), set(SOURCE_ORDER))
            self.assertEqual(report["age_days"], 0)

            manifest_path = snapshot / "manifest.json"
            original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stale_manifest = {**original_manifest, "created_at": "2020-01-01T00:00:00Z"}
            manifest_path.write_text(
                json.dumps(stale_manifest, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(StaticReleaseError, "重新下載九個官方來源"):
                validate_snapshot(
                    snapshot / "raw",
                    manifest_path,
                    allow_small_fixtures=True,
                    max_age_days=14,
                )
            manifest_path.write_text(
                json.dumps(original_manifest, ensure_ascii=False), encoding="utf-8"
            )

            tampered = snapshot / "raw" / "nhi_items.raw"
            tampered.write_bytes(tampered.read_bytes() + b"\n")
            with self.assertRaisesRegex(StaticReleaseError, "SHA-256"):
                validate_snapshot(
                    snapshot / "raw",
                    snapshot / "manifest.json",
                    allow_small_fixtures=True,
                )
