#!/usr/bin/env python3
"""Revalidate an existing nine-source snapshot before any label API calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline.static_release import (
    StaticReleaseError,
    atomic_json,
    official_snapshot_age_days,
    validated_source_snapshot,
)


def validate_snapshot(
    source_dir: Path,
    manifest_path: Path,
    *,
    allow_small_fixtures: bool = False,
    max_age_days: int | None = None,
) -> dict:
    manifest, bundles = validated_source_snapshot(
        source_dir,
        manifest_path,
        allow_small_fixtures=allow_small_fixtures,
    )
    age_days = official_snapshot_age_days(manifest["created_at"])
    if max_age_days is not None:
        if max_age_days < 0:
            raise ValueError("官方來源 snapshot 年齡上限不可小於零")
        if age_days > max_age_days:
            raise StaticReleaseError(
                f"官方來源 snapshot 已 {age_days} 天，超過 {max_age_days} 天門檻；"
                "請重新下載九個官方來源"
            )
    return {
        "schema_version": 1,
        "ready": True,
        "snapshot_id": manifest["snapshot_id"],
        "created_at": manifest["created_at"],
        "age_days": age_days,
        "sources": {
            name: {
                "sha256": bundle["content_hash"],
                "source_records": bundle["source_record_count"],
                "normalized_records": bundle["normalized_record_count"],
            }
            for name, bundle in bundles.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-small-fixtures", action="store_true")
    parser.add_argument("--max-age-days", type=int)
    args = parser.parse_args()
    report = validate_snapshot(
        args.source_dir,
        args.manifest,
        allow_small_fixtures=args.allow_small_fixtures,
        max_age_days=args.max_age_days,
    )
    atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
