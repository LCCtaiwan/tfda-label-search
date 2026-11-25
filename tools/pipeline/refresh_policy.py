"""Select a scheduled snapshot mode without hiding validation failures."""

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline.static_release import SOURCE_ORDER, official_snapshot_age_days


def source_mode(official_dir: Path, requested: str, scheduled: bool) -> str:
    if not scheduled:
        return requested
    manifest = official_dir / "manifest.json"
    if not manifest.is_file() or any(not (official_dir / "raw" / f"{name}.raw").is_file() for name in SOURCE_ORDER):
        return "refresh_all_nine"
    # Malformed or future timestamps fail closed; only missing/stale data auto-refresh.
    snapshot = json.loads(manifest.read_text(encoding="utf-8"))
    return "refresh_all_nine" if official_snapshot_age_days(snapshot.get("created_at")) > 14 else "reuse_existing"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-dir", type=Path, required=True)
    parser.add_argument("--requested", choices=("reuse_existing", "refresh_all_nine"), required=True)
    parser.add_argument("--scheduled", choices=("true", "false"), required=True)
    args = parser.parse_args()
    print("mode=" + source_mode(args.official_dir, args.requested, args.scheduled == "true"))
