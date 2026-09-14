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
            key = (str(document.get("approved_at") or ""), str(document.get("version") or ""))
            previous = current.get(number)
            previous_key = (
                str(previous.get("approved_at") or ""), str(previous.get("version") or "")
            ) if previous else ("", "")
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

    pdf_links: dict[str, list[str]] = defaultdict(list)
    for row in bundles["pdf_catalog"]["records"]:
        number = str(row.get("許可證字號") or "").strip()
        if number not in active:
            continue
        for value in str(row.get("仿單圖檔連結") or "").split(";"):
            value = value.strip()
            if value:
                parsed = urllib.parse.urlsplit(value)
                if parsed.scheme != "https" or parsed.hostname != "mcp.fda.gov.tw":
                    raise StaticReleaseError(f"{number} 的仿單備援不是 TFDA HTTPS 網址")
                if value not in pdf_links[number]:
                    pdf_links[number].append(value)
    return ingredients, nhi_items, events, {"links": pdf_links, "nhi_linkage": nhi_linkage}


def make_release_documents(
    active: dict[str, dict], structured: dict[str, dict], bundles: dict[str, dict]
) -> tuple[list[dict], dict]:
    ingredients, nhi_items, events, extra = group_enrichment(bundles, active)
    result = []
    structured_count = 0
    for number in sorted(active):
        catalog = active[number]
        if number in structured:
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
                    "content_text": "此藥證目前沒有可供全文搜尋的結構化電子仿單文字，請開啟官方來源確認。",
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
            }
            for item in nhi_items[number]
        ]
        document["event_types"] = sorted({item["event_type"] for item in events[number]})
        document["pdf_urls"] = extra["links"][number]
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

    release_root = args.release_root.resolve()
    target = release_root / "releases" / args.release_id
    if target.exists():
        raise StaticReleaseError(f"release 已存在，不可覆寫：{args.release_id}")
    release_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{args.release_id}-", dir=release_root))
    try:
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
            official.atomic_write(temporary / "sources" / f"{name}.json", bundle)

        active = active_catalog(bundles["licenses"])
        structured = load_documents(args.structured)
        documents, coverage = make_release_documents(active, structured, bundles)
        if coverage["structured_coverage"] < args.min_structured_coverage:
            raise StaticReleaseError(
                f"結構化仿單涵蓋率 {coverage['structured_coverage']:.2%} "
                f"低於門檻 {args.min_structured_coverage:.2%}"
            )

        document_bundle = {
            "schema_version": 1,
            "retrieved_at": now_iso(),
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

        manifest = {
            "schema_version": 1,
            "release_id": args.release_id,
            "created_at": now_iso(),
            "ready": True,
            "coverage": coverage,
            "source_hashes": {name: bundle["content_hash"] for name, bundle in bundles.items()},
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
    parser.add_argument("--structured", type=Path, action="append", required=True)
    parser.add_argument("--min-structured-coverage", type=float, default=0.98)
    parser.add_argument("--allow-small-fixtures", action="store_true")
    parser.add_argument("--activate", action="store_true")
    return parser.parse_args()


def main() -> None:
    report = build_release(parse_args())
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
