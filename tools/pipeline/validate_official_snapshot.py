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

from tools.pipeline.static_release import atomic_json, validated_source_snapshot


def validate_snapshot(
    source_dir: Path,
    manifest_path: Path,
    *,
    allow_small_fixtures: bool = False,
) -> dict:
    manifest, bundles = validated_source_snapshot(
        source_dir,
        manifest_path,
        allow_small_fixtures=allow_small_fixtures,
    )
    return {
        "schema_version": 1,
        "ready": True,
        "snapshot_id": manifest["snapshot_id"],
        "created_at": manifest["created_at"],
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
    args = parser.parse_args()
    report = validate_snapshot(
        args.source_dir,
        args.manifest,
        allow_small_fixtures=args.allow_small_fixtures,
    )
    atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
