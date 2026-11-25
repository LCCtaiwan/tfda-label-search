#!/usr/bin/env python3
"""Fetch resumable TFDA structured-label updates in official 10-day windows."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Callable
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.inserts.tfda_structured import Query, fetch_xml, parse_xml
from tools.pipeline.fetch_structured import RateLimiter
from tools.pipeline.static_release import active_catalog, atomic_json, document_order, license_code
from tools.sources import official


class UpdateBatchError(RuntimeError):
    """An update window failed; the last successful cursor remains usable."""


TERMINAL_INITIAL_STATUSES = {"downloaded", "no_document", "unqueryable"}


def closed_through_date() -> date:
    """Use the last fully closed Taiwan calendar day, never a partial current day."""
    return datetime.now(ZoneInfo("Asia/Taipei")).date() - timedelta(days=1)


def initial_state(output_dir: Path, catalog_hash: str, active: dict[str, dict]) -> dict:
    path = output_dir / "state.json"
    if not path.is_file():
        raise UpdateBatchError("初次逐藥證建庫尚未建立 state.json")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1 or not isinstance(state.get("items"), dict):
        raise UpdateBatchError("初次逐藥證建庫狀態格式錯誤")
    if state.get("catalog_hash") != catalog_hash:
        raise UpdateBatchError("初次建庫與目前藥證清單版本不同")
    pending = [
        number for number in active
        if state["items"].get(number, {}).get("status") not in TERMINAL_INITIAL_STATUSES
    ]
    if pending:
        raise UpdateBatchError(f"初次逐藥證建庫尚有 {len(pending)} 張未完成")
    return state


def newest_document(existing_path: Path, incoming: list[dict]) -> dict:
    documents = []
    if existing_path.is_file():
        previous = json.loads(existing_path.read_text(encoding="utf-8"))
        if previous.get("schema_version") != 1 or not isinstance(previous.get("documents"), list):
            raise UpdateBatchError(f"既有結構化仿單格式錯誤：{existing_path.name}")
        documents.extend(previous["documents"])
    documents.extend(incoming)
    by_version = {}
    for document in documents:
        key = (
            str(document.get("license_no") or ""),
            str(document.get("approved_at") or ""),
            str(document.get("version") or ""),
        )
        by_version[key] = document
    return max(
        by_version.values(),
        key=document_order,
    )


def windows(start: date, end: date, maximum: int) -> list[tuple[date, date]]:
    result = []
    cursor = start
    while cursor <= end and len(result) < maximum:
        window_end = min(cursor + timedelta(days=9), end)
        result.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return result


def fetch_updates(
    license_source: Path,
    output_dir: Path,
    *,
    start_date: date | None,
    through_date: date,
    max_windows: int = 1,
    request_delay: float = 2.0,
    fetch: Callable[[Query], bytes] = fetch_xml,
) -> dict:
    if not 1 <= max_windows <= 100:
        raise ValueError("每批日期區間必須是 1 到 100")
    bundle = official.build_bundle("licenses", license_source.read_bytes(), allow_small=True)
    active = active_catalog(bundle)
    output_dir.mkdir(parents=True, exist_ok=True)
    build_state = initial_state(output_dir, bundle["content_hash"], active)
    state_path = output_dir / "updates-state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != 1 or not state.get("next_date"):
            raise UpdateBatchError("增量更新狀態檔格式錯誤")
        cursor = date.fromisoformat(state["next_date"])
    elif start_date:
        cursor = start_date
        state = {"schema_version": 1, "next_date": cursor.isoformat()}
    else:
        raise ValueError("第一次增量更新必須提供 start_date")
    state["catalog_hash"] = bundle["content_hash"]
    atomic_json(state_path, state)
    build_state["incremental_initialized"] = True
    atomic_json(output_dir / "state.json", build_state)

    limiter = RateLimiter(request_delay)
    report = {"windows": 0, "documents": 0, "updated_licenses": 0, "ignored_inactive": 0}
    for window_start, window_end in windows(cursor, through_date, max_windows):
        query = Query(start_date=window_start.isoformat(), end_date=window_end.isoformat())
        try:
            limiter.wait()
            parsed = parse_xml(fetch(query), query)
            by_license: dict[str, list[dict]] = defaultdict(list)
            for document in parsed["documents"]:
                number = document["license_no"]
                if number not in active:
                    report["ignored_inactive"] += 1
                    continue
                by_license[number].append(document)
            for number, documents in by_license.items():
                code = active[number].get("license_code") or license_code(number)
                if not code:
                    continue
                destination = output_dir / "documents" / code[:2] / f"{code}.json"
                latest = newest_document(destination, documents)
                output = dict(parsed)
                output["documents"] = [latest]
                output["document_count"] = 1
                atomic_json(destination, output)
                build_state["items"][number] = {
                    "status": "downloaded",
                    "license_code": code,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
                report["documents"] += len(documents)
                report["updated_licenses"] += 1
            atomic_json(output_dir / "state.json", build_state)
        except Exception as exc:
            state["last_error"] = {
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "category": type(exc).__name__,
                "message": str(exc)[:500],
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            atomic_json(state_path, state)
            raise UpdateBatchError(
                f"{window_start} 至 {window_end} 更新失敗，續傳游標未前進"
            ) from exc
        state.pop("last_error", None)
        state["next_date"] = (window_end + timedelta(days=1)).isoformat()
        state["last_completed_window"] = {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(state_path, state)
        report["windows"] += 1

    next_date = date.fromisoformat(state["next_date"])
    report["next_date"] = next_date.isoformat()
    report["complete"] = next_date > through_date
    report["remaining_days"] = max(0, (through_date - next_date).days + 1)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--license-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--through-date", type=date.fromisoformat)
    parser.add_argument("--max-windows", type=int, default=1)
    parser.add_argument("--request-delay", type=float, default=2.0)
    args = parser.parse_args()
    report = fetch_updates(
        args.license_source,
        args.output_dir,
        start_date=args.start_date,
        through_date=args.through_date or closed_through_date(),
        max_windows=args.max_windows,
        request_delay=args.request_delay,
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
