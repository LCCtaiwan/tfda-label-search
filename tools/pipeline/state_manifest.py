#!/usr/bin/env python3
"""Validate a data-state checkout and write a small auditable manifest."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline.static_release import SOURCE_ORDER, StaticReleaseError, active_catalog, atomic_json


TERMINAL_STATUSES = {"downloaded", "no_document", "unqueryable"}


def tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def summarize_state(state: dict, active: dict[str, dict], document_files: list[Path]) -> dict:
    if state.get("schema_version") != 1 or not isinstance(state.get("items"), dict):
        raise StaticReleaseError("結構化仿單續傳狀態格式錯誤")
    items = state["items"]
    retired = set(items) - set(active)
    statuses = Counter(str(item.get("status") or "missing") for item in items.values())
    terminal = sum(1 for number in active if items.get(number, {}).get("status") in TERMINAL_STATUSES)
    downloaded = sum(1 for number in active if items.get(number, {}).get("status") == "downloaded")
    if len(document_files) < downloaded:
        raise StaticReleaseError("標示已下載的仿單數量大於實際文件數")
    pending = len(active) - terminal
    return {
        "active_licenses": len(active),
        "checked_licenses": terminal,
        "downloaded_licenses": downloaded,
        "pending_licenses": pending,
        "document_files": len(document_files),
        "retired_state_items": len(retired),
        "checked_coverage": terminal / len(active),
        "structured_coverage": downloaded / len(active),
        "complete": pending == 0,
        "statuses": dict(sorted(statuses.items())),
    }


def build_manifest(official_dir: Path, structured_dir: Path) -> dict:
    official_dir = official_dir.resolve()
    structured_dir = structured_dir.resolve()
    source_manifest = json.loads((official_dir / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("ready") is not True or set(source_manifest.get("sources", {})) != set(SOURCE_ORDER):
        raise StaticReleaseError("官方來源 snapshot 尚未完整通過")
    license_bundle = json.loads((official_dir / "normalized" / "licenses.json").read_text(encoding="utf-8"))
    active = active_catalog(license_bundle)
    state = json.loads((structured_dir / "state.json").read_text(encoding="utf-8"))
    if state.get("catalog_hash") != license_bundle.get("content_hash"):
        raise StaticReleaseError("續傳狀態使用的藥證清單不是目前版本")
    documents = sorted((structured_dir / "documents").rglob("*.json"))
    summary = summarize_state(state, active, documents)
    files = [
        *(path for path in official_dir.rglob("*") if path.is_file()),
        *(path for path in structured_dir.rglob("*") if path.is_file()),
    ]
    common_root = Path(os.path.commonpath([official_dir, structured_dir]))
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "official_snapshot_id": source_manifest["snapshot_id"],
        "official_snapshot_created_at": source_manifest["created_at"],
        "catalog_hash": license_bundle["content_hash"],
        "data_sha256": tree_hash(files, common_root),
        **summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-dir", type=Path, required=True)
    parser.add_argument("--structured-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.official_dir, args.structured_dir)
    atomic_json(args.output, manifest)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
