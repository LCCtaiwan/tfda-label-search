#!/usr/bin/env python3
"""Run either one initial license batch or bounded incremental update windows."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.inserts.tfda_structured import Query, fetch_xml
from tools.pipeline.fetch_structured import fetch_batch
from tools.pipeline.fetch_updates import closed_through_date, fetch_updates
from tools.pipeline.static_release import atomic_json


class IncrementalAuthorizationError(RuntimeError):
    """The next date-window request was not explicitly authorized."""


def sync_structured(
    license_source: Path,
    output_dir: Path,
    *,
    max_initial_items: int = 100,
    max_update_windows: int = 1,
    allow_incremental: bool = False,
    request_delay: float = 2.0,
    through_date: date,
    fetch_initial: Callable[[Query], bytes] = fetch_xml,
    fetch_incremental: Callable[[Query], bytes] = fetch_xml,
) -> dict:
    incremental_initialized = (output_dir / "updates-state.json").is_file()
    initial = fetch_batch(
        license_source,
        output_dir,
        max_items=max_initial_items,
        request_delay=request_delay,
        recheck_no_document_days=None if incremental_initialized else 30,
        fetch=fetch_initial,
    )
    report = {"schema_version": 1, "phase": "initial", "initial": initial}
    if not initial["complete"]:
        return report

    # Commit the final initial batch first. This avoids making another request
    # immediately after its last per-license request and gives a clean checkpoint.
    if initial["attempted"]:
        report["phase"] = "initial_complete"
        return report

    first_update = date.fromisoformat(initial["initial_started_on"])
    if not (output_dir / "updates-state.json").is_file() and first_update > through_date:
        report["phase"] = "waiting_for_closed_day"
        report["incremental"] = {
            "windows": 0,
            "documents": 0,
            "updated_licenses": 0,
            "ignored_inactive": 0,
            "next_date": first_update.isoformat(),
            "complete": True,
            "remaining_days": 0,
        }
        return report

    if not allow_incremental:
        raise IncrementalAuthorizationError(
            "下一步是 TFDA 日期增量查詢；10 日窗回傳的仿單份數由 TFDA 決定，"
            "必須另行明確授權"
        )
    report["phase"] = "incremental"
    report["incremental"] = fetch_updates(
        license_source,
        output_dir,
        start_date=first_update if not (output_dir / "updates-state.json").is_file() else None,
        through_date=through_date,
        max_windows=max_update_windows,
        request_delay=request_delay,
        fetch=fetch_incremental,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--license-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-initial-items", type=int, default=100)
    parser.add_argument("--max-update-windows", type=int, default=1)
    parser.add_argument(
        "--incremental-authorization",
        choices=("authorized", "not_authorized"),
        default="not_authorized",
    )
    parser.add_argument("--request-delay", type=float, default=2.0)
    parser.add_argument("--through-date", type=date.fromisoformat)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = sync_structured(
        args.license_source,
        args.output_dir,
        max_initial_items=args.max_initial_items,
        max_update_windows=args.max_update_windows,
        allow_incremental=args.incremental_authorization == "authorized",
        request_delay=args.request_delay,
        through_date=args.through_date or closed_through_date(),
    )
    atomic_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
