import json
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.official_snapshot import build_snapshot
from tools.pipeline.static_release import (
    SOURCE_ORDER,
    StaticReleaseError,
    build_release,
    document_order,
    license_code,
)
from tools.sources import official


ROOT = Path(__file__).resolve().parents[1]


def arguments(release_root: Path, release_id: str, coverage: float = 0.5) -> Namespace:
    return Namespace(
        release_id=release_id,
        release_root=release_root,
        source_dir=ROOT / "tests" / "fixtures" / "pipeline_sources",
        source_manifest=None,
        structured=[ROOT / "tests" / "fixtures" / "structured-real-sample.json"],
        min_structured_coverage=coverage,
        app_revision="a" * 40,
        data_revision="b" * 40,
        allow_small_fixtures=True,
        activate=True,
    )


class StaticReleaseTests(unittest.TestCase):
    def test_license_number_is_converted_to_official_api_code(self):
        self.assertEqual(license_code("衛署藥製字第016162號"), "01016162")
        self.assertEqual(license_code("衛部藥輸字第R00091號"), "52R00091")
        self.assertEqual(license_code("未知字第123456號"), "")

    def test_document_order_treats_version_ten_as_newer_than_nine(self):
        version_nine = {"approved_at": "114/09/15", "version": "9"}
        version_ten = {"approved_at": "2025-09-15", "version": "10"}
        self.assertGreater(document_order(version_ten), document_order(version_nine))

    def test_release_enriches_documents_and_marks_missing_text_honestly(self):
        with tempfile.TemporaryDirectory() as directory:
            release_root = Path(directory) / "release-root"
            manifest = build_release(arguments(release_root, "fixture-v1"))
            release = release_root / "releases" / "fixture-v1"
            documents = json.loads(
                (release / "documents.json").read_text(encoding="utf-8")
            )["documents"]
            by_license = {item["license_no"]: item for item in documents}

            self.assertTrue(manifest["ready"])
            self.assertEqual(manifest["coverage"]["active_licenses"], 2)
            self.assertEqual(manifest["coverage"]["structured_licenses"], 1)
            self.assertEqual(
                by_license["衛署藥製字第016162號"]["ingredients"][0]["name"],
                "TEST INGREDIENT",
            )
            self.assertEqual(
                by_license["衛署藥製字第016162號"]["nhi_items"][0]["code"],
                "A016162100",
            )
            missing = by_license["衛部藥製字第123456號"]
            self.assertEqual(missing["source_kind"], "metadata_only")
            self.assertIn("尚無結構化", missing["sections"][0]["title"])
            self.assertEqual(
                missing["pdf_urls"],
                ["https://mcp.fda.gov.tw/test/123456.pdf"],
            )
            self.assertTrue((release / "site" / "pagefind" / "pagefind.js").is_file())
            identity = json.loads(
                (release / "site" / "data" / "release.json").read_text(encoding="utf-8")
            )
            self.assertEqual(identity["release_id"], "fixture-v1")
            self.assertEqual(identity["app_revision"], "a" * 40)
            self.assertEqual(identity["data_revision"], "b" * 40)
            active = json.loads((release_root / "active.json").read_text(encoding="utf-8"))
            self.assertEqual(active["release_id"], "fixture-v1")

    def test_failed_candidate_does_not_replace_active_release(self):
        with tempfile.TemporaryDirectory() as directory:
            release_root = Path(directory) / "release-root"
            build_release(arguments(release_root, "fixture-v1"))
            with self.assertRaisesRegex(StaticReleaseError, "涵蓋率"):
                build_release(arguments(release_root, "fixture-v2", coverage=0.75))
            active = json.loads((release_root / "active.json").read_text(encoding="utf-8"))
            self.assertEqual(active["release_id"], "fixture-v1")
            self.assertFalse((release_root / "releases" / "fixture-v2").exists())

    def test_completed_release_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            release_root = Path(directory) / "release-root"
            build_release(arguments(release_root, "fixture-v1"))
            with self.assertRaisesRegex(StaticReleaseError, "不可覆寫"):
                build_release(arguments(release_root, "fixture-v1"))

    def test_production_release_requires_exact_git_revisions(self):
        args = arguments(Path("unused"), "fixture-v1")
        args.allow_small_fixtures = False
        args.app_revision = "main"
        with self.assertRaisesRegex(StaticReleaseError, "40 碼 Git SHA"):
            build_release(args)

    def test_production_release_requires_source_manifest(self):
        args = arguments(Path("unused"), "fixture-v1")
        args.allow_small_fixtures = False
        with self.assertRaisesRegex(StaticReleaseError, "snapshot manifest"):
            build_release(args)

    def test_release_uses_verified_snapshot_time_and_rejects_modified_raw(self):
        specs = official.load_sources()
        fixtures = ROOT / "tests" / "fixtures" / "pipeline_sources"
        payloads = {
            specs[name]["url"]: (fixtures / f"{name}.raw").read_bytes()
            for name in SOURCE_ORDER
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot_root = root / "snapshot-root"
            source_manifest = build_snapshot(
                snapshot_root,
                "traceable-v1",
                download=lambda url: payloads[url],
                allow_small_fixtures=True,
            )
            snapshot = snapshot_root / "snapshots" / "traceable-v1"
            args = arguments(root / "releases", "traceable-v1")
            args.source_dir = snapshot / "raw"
            args.source_manifest = snapshot / "manifest.json"
            build_release(args)
            release = root / "releases" / "releases" / "traceable-v1"
            identity = json.loads(
                (release / "site" / "data" / "release.json").read_text(encoding="utf-8")
            )
            search_manifest = json.loads(
                (release / "site" / "data" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(identity["official_snapshot_id"], "traceable-v1")
            self.assertEqual(
                identity["data_retrieved_at"], source_manifest["created_at"]
            )
            self.assertEqual(
                search_manifest["data_retrieved_at"], source_manifest["created_at"]
            )

            ingredient_path = snapshot / "raw" / "ingredients.raw"
            ingredient_path.write_bytes(ingredient_path.read_bytes() + b"\n")
            modified = arguments(root / "modified", "traceable-v2")
            modified.source_dir = snapshot / "raw"
            modified.source_manifest = snapshot / "manifest.json"
            with self.assertRaisesRegex(StaticReleaseError, "SHA-256"):
                build_release(modified)


if __name__ == "__main__":
    unittest.main()
