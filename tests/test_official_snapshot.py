import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.official_snapshot import build_snapshot
from tools.pipeline.static_release import SOURCE_ORDER
from tools.sources import official


ROOT = Path(__file__).resolve().parents[1]


class OfficialSnapshotTests(unittest.TestCase):
    def payloads(self):
        specs = official.load_sources()
        fixtures = ROOT / "tests" / "fixtures" / "pipeline_sources"
        return {specs[name]["url"]: (fixtures / f"{name}.raw").read_bytes()
                for name in SOURCE_ORDER}

    def test_all_sources_must_pass_before_active_snapshot_changes(self):
        payloads = self.payloads()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "official"
            report = build_snapshot(
                root,
                "fixture-v1",
                activate=True,
                download=lambda url: payloads[url],
                allow_small_fixtures=True,
            )
            self.assertTrue(report["ready"])
            self.assertEqual(set(report["sources"]), set(SOURCE_ORDER))
            self.assertTrue((root / "snapshots" / "fixture-v1" / "raw" / "licenses.raw").is_file())

            def fail_on_ingredients(url):
                if url == official.load_sources()["ingredients"]["url"]:
                    raise TimeoutError("temporary failure")
                return payloads[url]

            with self.assertRaises(TimeoutError):
                build_snapshot(
                    root,
                    "fixture-v2",
                    activate=True,
                    download=fail_on_ingredients,
                    allow_small_fixtures=True,
                )
            active = json.loads((root / "active.json").read_text(encoding="utf-8"))
            self.assertEqual(active["snapshot_id"], "fixture-v1")
            self.assertFalse((root / "snapshots" / "fixture-v2").exists())


if __name__ == "__main__":
    unittest.main()
