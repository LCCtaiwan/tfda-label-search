#!/usr/bin/env python3
"""Build an immutable, validated static TFDA label-search release."""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.sources import official


SOURCE_ORDER = (
    "licenses",
    "ingredients",
    "pdf_catalog",
    "recalls",
    "safety_alerts",
    "risk_management",
    "shortage_with_alternative",
    "shortage_without_alternative",
    "nhi_items",
)

LICENSE_PREFIX_CODES = {
    "衛署藥製": "01", "衛署藥輸": "02", "衛署成製": "03",
    "衛署菌疫製": "09", "衛署菌疫輸": "10", "內衛藥製": "12",
    "內衛藥輸": "13", "內衛成製": "14", "內衛菌疫製": "15",
    "內衛菌疫輸": "16", "衛署成輸": "19", "衛署罕藥輸": "20",
    "衛署罕藥製": "21", "衛署罕菌疫輸": "22", "衛署罕菌疫製": "23",
    "衛署藥陸輸": "41", "衛部藥製": "51", "衛部藥輸": "52",
    "衛部成製": "53", "衛部菌疫製": "59", "衛部菌疫輸": "60",
    "衛部成輸": "69", "衛部罕藥輸": "70", "衛部罕藥製": "71",
    "衛部罕菌疫輸": "72", "衛部罕菌疫製": "73", "衛部藥陸輸": "91",
}

class StaticReleaseError(RuntimeError):
    """The candidate release is unsafe to publish."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def official_snapshot_age_days(
    created_at: object,
    *,
    now: datetime | None = None,
) -> int:
    try:
        parsed = datetime.fromisoformat(str(created_at or "").replace("Z", "+00:00"))
    except ValueError as error:
        raise StaticReleaseError("官方來源 snapshot 建立時間格式錯誤") from error
    if parsed.tzinfo is None:
        raise StaticReleaseError("官方來源 snapshot 建立時間必須包含時區")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("目前時間必須包含時區")
    taipei = ZoneInfo("Asia/Taipei")
    age_days = (current.astimezone(taipei).date() - parsed.astimezone(taipei).date()).days
    if age_days < -1:
        raise StaticReleaseError("官方來源 snapshot 建立時間晚於今天")
    return max(0, age_days)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def license_code(license_no: str) -> str:
    compact = re.sub(r"\s+", "", str(license_no or ""))
    match = re.fullmatch(r"(.+?)字第([A-Z]?\d{5,6})號", compact, flags=re.I)
    if not match or match.group(1) not in LICENSE_PREFIX_CODES:
        return ""
    serial = match.group(2).upper()
    serial = serial.zfill(6) if serial.isdigit() else serial[0] + serial[1:].zfill(5)
    return LICENSE_PREFIX_CODES[match.group(1)] + serial if len(serial) == 6 else ""


def active_catalog(bundle: dict) -> dict[str, dict]:
    active: dict[str, dict] = {}
    for row in bundle.get("records", []):
        number = str(row.get("許可證字號") or "").strip()
        status = str(row.get("註銷狀態") or "").strip()
        if not number or status:
            continue
        active[number] = {
            "license_no": number,
            "license_code": license_code(number),
            "drug_name_zh": str(row.get("中文品名") or "").strip(),
            "drug_name_en": str(row.get("英文品名") or "").strip(),
        }
    if not active:
        raise StaticReleaseError("有效藥證清單為空")
    return active


def validated_source_snapshot(
    source_dir: Path,
    manifest_path: Path,
    *,
    allow_small_fixtures: bool = False,
) -> tuple[dict, dict[str, dict]]:
    """Re-parse every raw source and prove it still matches its snapshot manifest."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StaticReleaseError(f"無法讀取官方來源 manifest：{error}") from error
    sources = manifest.get("sources")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("ready") is not True
        or not isinstance(sources, dict)
        or set(sources) != set(SOURCE_ORDER)
    ):
        raise StaticReleaseError("官方來源 snapshot 尚未完整通過")
    snapshot_id = str(manifest.get("snapshot_id") or "").strip()
    created_at = str(manifest.get("created_at") or "").strip()
    if not snapshot_id or not created_at:
        raise StaticReleaseError("官方來源 snapshot 缺少版本或建立時間")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise StaticReleaseError("官方來源 snapshot 建立時間格式錯誤") from error
    if parsed_created_at.tzinfo is None:
        raise StaticReleaseError("官方來源 snapshot 建立時間必須包含時區")

    specs = official.load_sources()
    bundles = {}
    for name in SOURCE_ORDER:
        entry = sources[name]
        if not isinstance(entry, dict):
            raise StaticReleaseError(f"官方來源 manifest 的 {name} 格式錯誤")
        source_path = source_dir / f"{name}.raw"
        if not source_path.is_file():
            raise StaticReleaseError(f"缺少官方來源檔：{source_path.name}")
        payload = source_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if entry.get("url") != specs[name]["url"]:
            raise StaticReleaseError(f"官方來源 {name} 的網址與設定不符")
        if entry.get("sha256") != digest:
            raise StaticReleaseError(f"官方來源 {name} 的 SHA-256 與 snapshot 不符")
        bundle = official.build_bundle(
            name,
            payload,
            allow_small=allow_small_fixtures,
            retrieved_at=created_at,
        )
        if entry.get("source_records") != bundle["source_record_count"]:
            raise StaticReleaseError(f"官方來源 {name} 的原始筆數與 snapshot 不符")
        if entry.get("normalized_records") != bundle["normalized_record_count"]:
            raise StaticReleaseError(f"官方來源 {name} 的整理筆數與 snapshot 不符")
        bundles[name] = bundle
    return manifest, bundles


def natural_version_key(value: object) -> tuple:
    parts = re.findall(r"\d+|\D+", str(value or "").strip().casefold())
    return tuple((1, int(part)) if part.isdigit() else (0, part) for part in parts)


def document_order(document: dict) -> tuple:
    raw_date = str(document.get("approved_at") or "").strip()
    return (official.parse_date(raw_date) or raw_date, natural_version_key(document.get("version")))


def load_documents(paths: list[Path]) -> dict[str, dict]:
    current: dict[str, dict] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or not isinstance(payload.get("documents"), list):
            raise StaticReleaseError(f"{path} 不是支援的結構化仿單 JSON")
        if payload.get("document_count") != len(payload["documents"]):
            raise StaticReleaseError(f"{path} 的 document_count 不正確")
        for raw in payload["documents"]:
            document = deepcopy(raw)
            number = str(document.get("license_no") or "").strip()
            if not number or not isinstance(document.get("sections"), list):
                raise StaticReleaseError(f"{path} 含有缺少藥證或章節的文件")
            if document.get("source_kind") not in (
                "tfda_structured_insert", "metadata_only", "no_document"
            ):
                raise StaticReleaseError(f"{path} 含非結構化仿單來源")
            key = document_order(document)
            previous = current.get(number)
            previous_key = document_order(previous) if previous else ("", ())
            if previous is None or key > previous_key:
                current[number] = document
    return current


def group_enrichment(bundles: dict[str, dict], active: dict[str, dict]) -> tuple[dict, dict, dict, dict]:
    ingredients: dict[str, list[dict]] = defaultdict(list)
    for item in bundles["ingredients"]["records"]:
        if item.get("license_no") in active:
            ingredients[item["license_no"]].append(item)

    by_code: dict[str, list[str]] = defaultdict(list)
    for number, item in active.items():
        if item["license_code"]:
            by_code[item["license_code"]].append(number)
    nhi_items: dict[str, list[dict]] = defaultdict(list)
    nhi_linkage = {"matched": 0, "unresolved": 0, "ambiguous": 0, "missing_official_id": 0}
    for item in bundles["nhi_items"]["records"]:
        identifier = str(item.get("official_license_id") or "")
        candidates = by_code.get(identifier, []) if identifier else []
        if not identifier:
            status = "missing_official_id"
        elif len(candidates) == 1:
            status = "matched"
            nhi_items[candidates[0]].append(item)
        elif len(candidates) > 1:
            status = "ambiguous"
        else:
            status = "unresolved"
        nhi_linkage[status] += 1

    events: dict[str, list[dict]] = defaultdict(list)
    for name in SOURCE_ORDER:
        if bundles[name]["kind"] != "events":
            continue
        for event in bundles[name]["records"]:
            for reference in event.get("licenses", []):
                number = reference.get("license_no")
                if number in active:
                    events[number].append(event)

    return ingredients, nhi_items, events, {"nhi_linkage": nhi_linkage}


def make_release_documents(
    active: dict[str, dict], structured: dict[str, dict], bundles: dict[str, dict]
) -> tuple[list[dict], dict]:
    ingredients, nhi_items, events, extra = group_enrichment(bundles, active)
    result = []
    structured_count = 0
    for number in sorted(active):
        catalog = active[number]
        if (number in structured
            and structured[number].get("source_kind") == "tfda_structured_insert"
            and any(
                str(section.get("content_text") or "").strip()
                for section in structured[number]["sections"]
            )
        ):
            document = deepcopy(structured[number])
            structured_count += 1
        else:
            document = {
                "license_no": number,
                "version": "",
                "approved_at": "",
                "source_kind": "metadata_only",
                "sections": [{
                    "id": "metadata-only",
                    "parent_id": "",
                    "level": 1,
                    "number": "",
                    "title": "尚無結構化電子仿單文字",
                    "path": ["資料涵蓋狀態", "尚無結構化電子仿單文字"],
                    "content_text": "此藥證尚無結構化仿單文字，請開啟食藥署仿單頁確認；不保證該頁有仿單。",
                    "search_text": "尚無結構化電子仿單文字",
                }],
            }
        document["drug_name_zh"] = str(document.get("drug_name_zh") or catalog["drug_name_zh"])
        document["drug_name_en"] = str(document.get("drug_name_en") or catalog["drug_name_en"])
        document["license_code"] = catalog["license_code"]
        document["ingredients"] = [
            {"name": item["ingredient_name"], "amount_description": item["amount_description"]}
            for item in ingredients[number]
        ]
        document["nhi_items"] = [
            {
                "code": item["nhi_code"],
                "atc_code": item["atc_code"],
                "benefit_chapter": item["benefit_chapter"],
                "specification": item["specification"],
                "price": item["price"],
                "effective_from": item["effective_from"],
                "effective_until": item["effective_until"],
                "company": item["company"],
                "dosage_form": item["dosage_form"],
                "item_url": item["item_url"],
                "rule_url": item["rule_url"],
            }
            for item in nhi_items[number]
        ]
        public_events = []
        seen_events = set()
        for item in sorted(
            events[number],
            key=lambda event: (
                str(event.get("published_on") or ""),
                str(event.get("event_type") or ""),
                str(event.get("source_key") or ""),
            ),
            reverse=True,
        ):
            event_key = (item.get("event_type"), item.get("source_key"))
            if event_key in seen_events:
                continue
            seen_events.add(event_key)
            public_events.append({
                "event_type": str(item.get("event_type") or ""),
                "published_on": str(item.get("published_on") or ""),
                "title": str(item.get("title") or ""),
                "status": str(item.get("status") or ""),
                "source_url": str(item.get("source_url") or ""),
            })
        document["official_events"] = public_events
        document["event_types"] = sorted({item["event_type"] for item in public_events})
        # Legacy file links never enter release or search data.
        document.pop("pdf_urls", None)
        document["official_url"] = (
            "https://mcp.fda.gov.tw/im_detail_1/" + urllib.parse.quote(number, safe="")
        )
        result.append(document)
    counts = {
        "active_licenses": len(active),
        "structured_licenses": structured_count,
        "metadata_only_licenses": len(active) - structured_count,
        "structured_coverage": structured_count / len(active),
        "nhi_linkage": extra["nhi_linkage"],
    }
    return result, counts


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_release(args: argparse.Namespace) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.release_id):
        raise StaticReleaseError("release id 格式不安全")
    if not 0 <= args.min_structured_coverage <= 1:
        raise StaticReleaseError("涵蓋率門檻必須介於 0 與 1")
    app_revision = str(getattr(args, "app_revision", "") or "").strip().lower()
    data_revision = str(getattr(args, "data_revision", "") or "").strip().lower()
    for name, revision in (("app", app_revision), ("data", data_revision)):
        if revision and not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise StaticReleaseError(f"{name} revision 必須是完整 40 碼 Git SHA")
    if not args.allow_small_fixtures and (not app_revision or not data_revision):
        raise StaticReleaseError("正式 release 必須記錄 app 與 data 的完整 Git SHA")
    source_manifest = getattr(args, "source_manifest", None)
    if not args.allow_small_fixtures and not source_manifest:
        raise StaticReleaseError("正式 release 必須提供官方來源 snapshot manifest")

    release_root = args.release_root.resolve()
    target = release_root / "releases" / args.release_id
    if target.exists():
        raise StaticReleaseError(f"release 已存在，不可覆寫：{args.release_id}")
    release_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{args.release_id}-", dir=release_root))
    try:
        source_snapshot = None
        if source_manifest:
            source_snapshot, bundles = validated_source_snapshot(
                args.source_dir,
                Path(source_manifest),
                allow_small_fixtures=args.allow_small_fixtures,
            )
            max_snapshot_age = getattr(args, "max_official_snapshot_age_days", None)
            snapshot_age = official_snapshot_age_days(source_snapshot["created_at"])
            if max_snapshot_age is not None:
                if max_snapshot_age < 0:
                    raise ValueError("官方來源 snapshot 年齡上限不可小於零")
                if snapshot_age > max_snapshot_age:
                    raise StaticReleaseError(
                        f"官方來源 snapshot 已 {snapshot_age} 天，"
                        f"超過 {max_snapshot_age} 天門檻"
                    )
        else:
            snapshot_age = None
            bundles = {}
            for name in SOURCE_ORDER:
                source_path = args.source_dir / f"{name}.raw"
                if not source_path.is_file():
                    raise StaticReleaseError(f"缺少官方來源檔：{source_path.name}")
                bundle = official.build_bundle(
                    name,
                    source_path.read_bytes(),
                    allow_small=args.allow_small_fixtures,
                )
                bundles[name] = bundle
        for name, bundle in bundles.items():
            # InfoId 39 remains in snapshot validation, never in release output.
            if name == "pdf_catalog":
                continue
            official.atomic_write(temporary / "sources" / f"{name}.json", bundle)

        active = active_catalog(bundles["licenses"])
        structured = load_documents(args.structured)
        documents, coverage = make_release_documents(active, structured, bundles)
        if coverage["structured_coverage"] < args.min_structured_coverage:
            raise StaticReleaseError(
                f"結構化仿單涵蓋率 {coverage['structured_coverage']:.2%} "
                f"低於門檻 {args.min_structured_coverage:.2%}"
            )

        data_retrieved_at = (
            source_snapshot["created_at"] if source_snapshot else now_iso()
        )
        document_bundle = {
            "schema_version": 1,
            "retrieved_at": data_retrieved_at,
            "source": {"provider": "TFDA/NHIA validated static release"},
            "document_count": len(documents),
            "documents": documents,
        }
        atomic_json(temporary / "documents.json", document_bundle)
        atomic_json(temporary / "coverage.json", {"schema_version": 1, **coverage})

        command = [
            "node", "scripts/build-pagefind.mjs", "--input",
            str(temporary / "documents.json"), "--output", str(temporary / "site"),
        ]
        completed = subprocess.run(
            command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600
        )
        if completed.returncode:
            raise StaticReleaseError(f"Pagefind 建置失敗：{completed.stderr.strip()}")

        created_at = now_iso()
        identity = {
            "schema_version": 1,
            "release_id": args.release_id,
            "created_at": created_at,
            "app_revision": app_revision,
            "data_revision": data_revision,
            "official_snapshot_id": source_snapshot["snapshot_id"] if source_snapshot else "",
            "official_snapshot_age_days": snapshot_age,
            "data_retrieved_at": data_retrieved_at,
            "coverage": coverage,
            "source_hashes": {name: bundle["content_hash"] for name, bundle in bundles.items()},
        }
        atomic_json(temporary / "site" / "data" / "release.json", identity)
        manifest = {
            **identity,
            "ready": True,
            "release_sha256": tree_hash(temporary),
        }
        atomic_json(temporary / "manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)

        if args.activate:
            atomic_json(release_root / "active.json", {
                "schema_version": 1,
                "release_id": args.release_id,
                "manifest": f"releases/{args.release_id}/manifest.json",
                "site": f"releases/{args.release_id}/site",
                "activated_at": now_iso(),
            })
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--structured", type=Path, action="append", default=[])
    parser.add_argument("--structured-dir", type=Path)
    parser.add_argument("--min-structured-coverage", type=float, default=0)
    parser.add_argument("--max-official-snapshot-age-days", type=int)
    parser.add_argument("--app-revision", default="")
    parser.add_argument("--data-revision", default="")
    parser.add_argument("--allow-small-fixtures", action="store_true")
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    if args.structured_dir:
        args.structured.extend(sorted(args.structured_dir.rglob("*.json")))
    if not args.structured and not args.structured_dir:
        parser.error("至少需要一個 --structured 或含 JSON 的 --structured-dir")
    return args


def main() -> None:
    report = build_release(parse_args())
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
