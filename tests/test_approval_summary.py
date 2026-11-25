import json
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.approval_summary import ApprovalSummaryError, build_approval_summary


def write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def evidence(root: Path) -> dict[str, Path]:
    coverage = {
        "schema_version": 1,
        "active_licenses": 100,
        "structured_licenses": 98,
        "metadata_only_licenses": 2,
        "structured_coverage": 0.98,
        "nhi_linkage": {
            "matched": 80,
            "unresolved": 1,
            "ambiguous": 1,
            "missing_official_id": 2,
        },
    }
    manifest_coverage = {key: value for key, value in coverage.items() if key != "schema_version"}
    return {
        "manifest": write(root / "manifest.json", {
            "schema_version": 1,
            "ready": True,
            "release_id": "release-1",
            "app_revision": "a" * 40,
            "data_revision": "b" * 40,
            "official_snapshot_id": "snapshot-1",
            "official_snapshot_age_days": 2,
            "data_retrieved_at": "2026-09-15T00:00:00Z",
            "coverage": manifest_coverage,
            "source_hashes": {name: "c" * 64 for name in (
                "licenses", "ingredients", "pdf_catalog", "recalls", "safety_alerts",
                "risk_management", "shortage_with_alternative",
                "shortage_without_alternative", "nhi_items",
            )},
        }),
        "coverage": write(root / "coverage.json", coverage),
        "data_state": write(root / "data-state.json", {
            "schema_version": 1,
            "complete": True,
            "incremental_initialized": True,
            "official_snapshot_id": "snapshot-1",
            "official_snapshot_age_days": 2,
            "incremental_lag_days": 1,
            "active_licenses": 100,
            "downloaded_licenses": 98,
            "structured_coverage": 0.98,
        }),
        "preflight": write(root / "preflight.json", {
            "schema_version": 1,
            "ready": True,
            "checks": [
                "policy_review_current",
                "official_open_data_verified",
                "official_dataset_scope_verified",
                "structured_plain_text_only",
                "third_party_not_included",
                "visible_provider_attribution",
                "visible_license_notice",
                "visible_disclaimer",
            ],
        }),
        "synonyms": write(root / "synonyms.json", {
            "schema_version": 1,
            "entries": [{
                "terms": ["掉髮", "脫髮"],
                "reviewed": True,
                "reviewer": "test",
                "reviewed_at": "2026-09-15",
            }],
        }),
    }


class ApprovalSummaryTests(unittest.TestCase):
    def test_builds_human_readable_cross_checked_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            files = evidence(Path(directory))
            summary = build_approval_summary(**{
                f"{name}_path": path for name, path in files.items()
            })
            self.assertIn("TFDA Pages 主管核准摘要", summary)
            self.assertIn("98（98.00%", summary)
            self.assertIn("成功 80／找不到 1／不唯一 1", summary)
            self.assertIn("1 組、2 詞", summary)
            self.assertIn("尚無結構化仿單（連食藥署仿單頁） | 2", summary)
            self.assertNotIn("只有官方檔案", summary)
            self.assertIn("程式 commit", summary)
            self.assertIn("請按 **Reject**", summary)

    def test_rejects_mismatched_or_stale_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = evidence(root)
            manifest = json.loads(files["manifest"].read_text())
            manifest["coverage"]["structured_licenses"] = 99
            write(files["manifest"], manifest)
            with self.assertRaisesRegex(ApprovalSummaryError, "不一致"):
                build_approval_summary(**{
                    f"{name}_path": path for name, path in files.items()
                })

            files = evidence(root)
            state = json.loads(files["data_state"].read_text())
            state["official_snapshot_age_days"] = 15
            write(files["data_state"], state)
            manifest = json.loads(files["manifest"].read_text())
            manifest["official_snapshot_age_days"] = 15
            write(files["manifest"], manifest)
            with self.assertRaisesRegex(ApprovalSummaryError, "超過"):
                build_approval_summary(**{
                    f"{name}_path": path for name, path in files.items()
                })


if __name__ == "__main__":
    unittest.main()
