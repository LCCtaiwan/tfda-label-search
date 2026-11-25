import json
from argparse import Namespace
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from tools.pipeline.official_snapshot import build_snapshot
from tools.pipeline.static_release import (
    SOURCE_ORDER,
    StaticReleaseError,
    build_release,
    active_catalog,
    document_order,
    license_code,
    load_documents,
    make_release_documents,
    official_snapshot_age_days,
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
    def test_snapshot_age_uses_taipei_calendar(self):
        now = datetime.fromisoformat("2026-09-16T00:00:00+08:00")
        self.assertEqual(
            official_snapshot_age_days("2026-09-01T16:30:00Z", now=now),
            14,
        )
        with self.assertRaisesRegex(StaticReleaseError, "晚於今天"):
            official_snapshot_age_days("2026-09-18T00:00:00+08:00", now=now)

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
            self.assertEqual(manifest["coverage"]["metadata_only_licenses"], 1)
            self.assertFalse(any("file" in key for key in manifest["coverage"]))
            self.assertEqual(
                by_license["衛署藥製字第016162號"]["ingredients"][0]["name"],
                "TEST INGREDIENT",
            )
            self.assertEqual(
                by_license["衛署藥製字第016162號"]["nhi_items"][0]["code"],
                "A016162100",
            )
            nhi_item = by_license["衛署藥製字第016162號"]["nhi_items"][0]
            self.assertEqual(nhi_item["price"], "1.5")
            self.assertEqual(nhi_item["effective_from"], "2026-01-01")
            self.assertEqual(nhi_item["specification"], "10 MG")
            self.assertEqual(nhi_item["company"], "測試公司")
            self.assertEqual(nhi_item["dosage_form"], "TABLET")
            self.assertEqual(nhi_item["rule_url"], "https://info.nhi.gov.tw/rule")
            official_events = by_license["衛署藥製字第016162號"][
                "official_events"
            ]
            self.assertEqual(len(official_events), 4)
            self.assertEqual(
                {item["event_type"] for item in official_events},
                {"recall", "safety_alert", "risk_management", "shortage_with_alternative"},
            )
            self.assertTrue(
                all(
                    item["source_url"].startswith("https://data.fda.gov.tw/")
                    for item in official_events
                )
            )
            missing = by_license["衛部藥製字第123456號"]
            self.assertEqual(missing["source_kind"], "metadata_only")
            self.assertIn("尚無結構化", missing["sections"][0]["title"])
            self.assertEqual(
                missing["official_url"],
                "https://mcp.fda.gov.tw/im_detail_1/"
                "%E8%A1%9B%E9%83%A8%E8%97%A5%E8%A3%BD%E5%AD%97%E7%AC%AC123456%E8%99%9F",
            )
            self.assertTrue((release / "site" / "pagefind" / "pagefind.js").is_file())
            identity = json.loads(
                (release / "site" / "data" / "release.json").read_text(encoding="utf-8")
            )
            self.assertEqual(identity["release_id"], "fixture-v1")
            self.assertEqual(identity["app_revision"], "a" * 40)
            self.assertEqual(identity["data_revision"], "b" * 40)
            public_coverage = json.loads(
                (release / "site" / "data" / "coverage.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(public_coverage["searchable_text_documents"], 1)
            self.assertEqual(public_coverage["metadata_only_documents"], 1)
            self.assertFalse((release / "sources" / "pdf_catalog.json").exists())
            for filename in release.rglob("*.json"):
                published = filename.read_text(encoding="utf-8")
                self.assertNotIn('"pdf_urls"', published, filename)
                self.assertNotIn("仿單圖檔連結", published, filename)
                self.assertNotIn("https://mcp.fda.gov.tw/test/", published, filename)
            active = json.loads((release_root / "active.json").read_text(encoding="utf-8"))
            self.assertEqual(active["release_id"], "fixture-v1")

    def test_empty_structured_insert_uses_metadata_and_ignores_file_catalog(self):
        bundles = {
            name: official.build_bundle(
                name, (ROOT / "tests/fixtures/pipeline_sources" / f"{name}.raw").read_bytes(),
                allow_small=True,
            ) for name in SOURCE_ORDER
        }
        active = active_catalog(bundles["licenses"])
        structured = load_documents([ROOT / "tests/fixtures/structured-real-sample.json"])
        number = next(iter(structured))
        structured[number]["pdf_urls"] = ["https://example.com/legacy.pdf"]
        # File-catalog contents must not affect published documents or coverage.
        before = make_release_documents(active, structured, bundles)
        bundles["pdf_catalog"]["records"] = []
        self.assertEqual(before, make_release_documents(active, structured, bundles))
        self.assertTrue(all("pdf_urls" not in doc for doc in before[0]))
        for section in structured[number]["sections"]:
            section["content_text"] = " "
        documents, coverage = make_release_documents(active, structured, bundles)
        self.assertEqual(coverage["structured_licenses"], 0)
        self.assertTrue(all(doc["source_kind"] == "metadata_only" for doc in documents))

    def test_rejects_pdf_text_as_structured_input(self):
        payload = json.loads((ROOT / "tests/fixtures/structured-real-sample.json").read_text())
        payload["documents"][0]["source_kind"] = "pdf_text"
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "input.json"
            filename.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(StaticReleaseError, "非結構化仿單來源"):
                load_documents([filename])

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
            self.assertEqual(identity["official_snapshot_age_days"], 0)

            manifest_path = snapshot / "manifest.json"
            stale_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stale_manifest["created_at"] = "2020-01-01T00:00:00Z"
            manifest_path.write_text(
                json.dumps(stale_manifest, ensure_ascii=False), encoding="utf-8"
            )
            stale = arguments(root / "stale", "traceable-stale")
            stale.source_dir = snapshot / "raw"
            stale.source_manifest = manifest_path
            stale.max_official_snapshot_age_days = 14
            with self.assertRaisesRegex(StaticReleaseError, "官方來源 snapshot 已"):
                build_release(stale)
            manifest_path.write_text(
                json.dumps(source_manifest, ensure_ascii=False), encoding="utf-8"
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
