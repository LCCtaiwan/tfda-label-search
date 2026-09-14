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
from tools.pipeline.fetch_updates import closed_through_date
from tools.sources import official


TERMINAL_STATUSES = {"downloaded", "no_document", "unqueryable"}
MAX_GIT_FILE_BYTES = 95 * 1024 * 1024


def tree_hash(paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_git_payload(paths: list[Path], root: Path, max_bytes: int = MAX_GIT_FILE_BYTES) -> dict:
    if max_bytes < 1:
        raise ValueError("Git 單檔上限必須大於零")
    largest = max(paths, key=lambda path: path.stat().st_size, default=None)
    largest_size = largest.stat().st_size if largest else 0
    if largest_size > max_bytes:
        raise StaticReleaseError(
            f"data-state 單檔超過 {max_bytes} bytes：{largest.relative_to(root)}"
        )
    return {
        "file_count": len(paths),
        "total_bytes": sum(path.stat().st_size for path in paths),
        "largest_file": largest.relative_to(root).as_posix() if largest else "",
        "largest_file_bytes": largest_size,
        "git_file_limit_bytes": max_bytes,
    }


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


def summarize_incremental(path: Path, catalog_hash: str) -> dict:
    if not path.is_file():
        return {
            "incremental_initialized": False,
            "incremental_next_date": "",
            "incremental_lag_days": None,
            "incremental_last_completed_end": "",
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1 or not state.get("next_date"):
        raise StaticReleaseError("結構化仿單增量狀態格式錯誤")
    if state.get("catalog_hash") != catalog_hash:
        raise StaticReleaseError("增量狀態使用的藥證清單不是目前版本")
    if state.get("last_error"):
        raise StaticReleaseError("增量狀態仍留有未解決錯誤")
    try:
        next_date = datetime.fromisoformat(str(state["next_date"])).date()
    except ValueError as error:
        raise StaticReleaseError("增量狀態 next_date 格式錯誤") from error
    lag_days = max(0, (closed_through_date() - next_date).days + 1)
    last_completed = state.get("last_completed_window") or {}
    return {
        "incremental_initialized": True,
        "incremental_next_date": next_date.isoformat(),
        "incremental_lag_days": lag_days,
        "incremental_last_completed_end": str(last_completed.get("end") or ""),
    }


def build_manifest(
    official_dir: Path,
    structured_dir: Path,
    *,
    allow_small_fixtures: bool = False,
    require_incremental: bool = False,
    max_incremental_lag_days: int | None = None,
) -> dict:
    official_dir = official_dir.resolve()
    structured_dir = structured_dir.resolve()
    source_manifest = json.loads((official_dir / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("ready") is not True or set(source_manifest.get("sources", {})) != set(SOURCE_ORDER):
        raise StaticReleaseError("官方來源 snapshot 尚未完整通過")
    license_bundle = official.build_bundle(
        "licenses",
        (official_dir / "raw" / "licenses.raw").read_bytes(),
        allow_small=allow_small_fixtures,
    )
    active = active_catalog(license_bundle)
    state = json.loads((structured_dir / "state.json").read_text(encoding="utf-8"))
    if state.get("catalog_hash") != license_bundle.get("content_hash"):
        raise StaticReleaseError("續傳狀態使用的藥證清單不是目前版本")
    documents = sorted((structured_dir / "documents").rglob("*.json"))
    summary = summarize_state(state, active, documents)
    incremental = summarize_incremental(
        structured_dir / "updates-state.json", license_bundle["content_hash"]
    )
    if require_incremental and not incremental["incremental_initialized"]:
        raise StaticReleaseError("初次建庫完成後尚未建立增量更新游標")
    if max_incremental_lag_days is not None:
        if max_incremental_lag_days < 0:
            raise ValueError("增量落後天數上限不可小於零")
        lag_days = incremental["incremental_lag_days"]
        if lag_days is None or lag_days > max_incremental_lag_days:
            raise StaticReleaseError(
                f"結構化仿單增量落後 {lag_days if lag_days is not None else '未知'} 天，"
                f"超過 {max_incremental_lag_days} 天門檻"
            )
    files = [
        *(path for path in official_dir.rglob("*") if path.is_file()),
        *(path for path in structured_dir.rglob("*") if path.is_file()),
    ]
    common_root = Path(os.path.commonpath([official_dir, structured_dir]))
    payload = validate_git_payload(files, common_root)
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "official_snapshot_id": source_manifest["snapshot_id"],
        "official_snapshot_created_at": source_manifest["created_at"],
        "catalog_hash": license_bundle["content_hash"],
        "data_sha256": tree_hash(files, common_root),
        **payload,
        **summary,
        **incremental,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-dir", type=Path, required=True)
    parser.add_argument("--structured-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-small-fixtures", action="store_true")
    parser.add_argument("--require-incremental", action="store_true")
    parser.add_argument("--max-incremental-lag-days", type=int)
    args = parser.parse_args()
    manifest = build_manifest(
        args.official_dir,
        args.structured_dir,
        allow_small_fixtures=args.allow_small_fixtures,
        require_incremental=args.require_incremental,
        max_incremental_lag_days=args.max_incremental_lag_days,
    )
    atomic_json(args.output, manifest)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
