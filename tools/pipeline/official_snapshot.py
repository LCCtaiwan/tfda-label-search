#!/usr/bin/env python3
"""Download all configured official datasets into one immutable snapshot."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline.static_release import SOURCE_ORDER, StaticReleaseError, atomic_json
from tools.sources import official


def build_snapshot(
    output_root: Path,
    snapshot_id: str,
    *,
    activate: bool = False,
    download: Callable[[str], bytes] = official.download,
    allow_small_fixtures: bool = False,
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", snapshot_id):
        raise StaticReleaseError("snapshot id 格式不安全")
    output_root = output_root.resolve()
    target = output_root / "snapshots" / snapshot_id
    if target.exists():
        raise StaticReleaseError(f"snapshot 已存在，不可覆寫：{snapshot_id}")
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{snapshot_id}-", dir=output_root))
    try:
        specs = official.load_sources()
        sources = {}
        for name in SOURCE_ORDER:
            payload = download(specs[name]["url"])
            bundle = official.build_bundle(
                name, payload, allow_small=allow_small_fixtures
            )
            raw_path = temporary / "raw" / f"{name}.raw"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(payload)
            official.atomic_write(temporary / "normalized" / f"{name}.json", bundle)
            sources[name] = {
                "url": specs[name]["url"],
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source_records": bundle["source_record_count"],
                "normalized_records": bundle["normalized_record_count"],
            }
        manifest = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ready": True,
            "sources": sources,
        }
        atomic_json(temporary / "manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
        if activate:
            atomic_json(output_root / "active.json", {
                "schema_version": 1,
                "snapshot_id": snapshot_id,
                "path": f"snapshots/{snapshot_id}",
                "activated_at": datetime.now(timezone.utc).isoformat(),
            })
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_snapshot(args.output_root, args.snapshot_id, activate=args.activate), ensure_ascii=False))


if __name__ == "__main__":
    main()
