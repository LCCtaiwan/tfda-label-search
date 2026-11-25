from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.refresh_policy import source_mode
from tools.pipeline.static_release import SOURCE_ORDER, StaticReleaseError


class RefreshPolicyTests(unittest.TestCase):
    def test_scheduled_missing_stale_fresh_and_boundary_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(source_mode(root, "reuse_existing", True), "refresh_all_nine")
            (root / "raw").mkdir()
            for name in SOURCE_ORDER:
                (root / "raw" / f"{name}.raw").touch()
            for days, expected in [(0, "reuse_existing"), (14, "reuse_existing"), (15, "refresh_all_nine")]:
                (root / "manifest.json").write_text(json.dumps({"created_at": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}))
                self.assertEqual(source_mode(root, "reuse_existing", True), expected)
            (root / "manifest.json").write_text(json.dumps({"created_at": "2099-01-01T00:00:00Z"}))
            with self.assertRaises(StaticReleaseError):
                source_mode(root, "reuse_existing", True)

    def test_manual_mode_is_never_silently_expanded(self):
        for requested in ("reuse_existing", "refresh_all_nine"):
            self.assertEqual(source_mode(Path("missing"), requested, False), requested)
