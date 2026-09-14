import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.release_preflight import run_preflight, validate_policy
from tools.pipeline.static_release import StaticReleaseError


ROOT = Path(__file__).resolve().parents[1]


class ReleasePreflightTests(unittest.TestCase):
    def policy(self):
        return json.loads((ROOT / "config" / "publication-policy.json").read_text(encoding="utf-8"))

    def test_current_policy_and_visible_attribution_pass(self):
        report = run_preflight(
            ROOT / "config" / "publication-policy.json",
            ROOT / "web",
            ROOT,
        )
        self.assertTrue(report["ready"])
        self.assertIn("structured_plain_text_only", report["checks"])
        self.assertEqual(len(report["policy_sha256"]), 64)

    def test_pending_structured_label_scope_stops_release(self):
        policy = self.policy()
        policy["structured_labels"]["status"] = "pending"
        with self.assertRaises(StaticReleaseError):
            validate_policy(policy, ROOT)

    def test_stale_policy_stops_release(self):
        policy = self.policy()
        policy["reviewed_at"] = "2020-01-01"
        with self.assertRaises(StaticReleaseError):
            validate_policy(policy, ROOT)

    def test_claiming_no_third_party_code_with_files_stops_release(self):
        policy = self.policy()
        policy["third_party_code"]["copied_files"] = ["web/app.js"]
        with self.assertRaises(StaticReleaseError):
            validate_policy(policy, ROOT)

    def test_missing_visible_license_notice_stops_release(self):
        with tempfile.TemporaryDirectory() as directory:
            site_root = Path(directory)
            source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
            (site_root / "index.html").write_text(
                source.replace("政府資料開放授權條款-第1版", "授權文字遺失"),
                encoding="utf-8",
            )
            with self.assertRaises(StaticReleaseError):
                run_preflight(ROOT / "config" / "publication-policy.json", site_root, ROOT)


if __name__ == "__main__":
    unittest.main()
