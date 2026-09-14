#!/usr/bin/env python3
"""Fetch a resumable, rate-limited batch of TFDA structured labels."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.inserts.tfda_structured import (
    APIResponseError,
    NoDocumentError,
    Query,
    fetch_xml,
    parse_xml,
)
from tools.pipeline.static_release import active_catalog, atomic_json, license_code
from tools.sources import official


class StructuredBatchError(RuntimeError):
    """A structured-label batch stopped and can be resumed."""


class RateLimiter:
    def __init__(self, seconds: float):
        if seconds < 0 or seconds > 30:
            raise ValueError("請求間隔必須介於 0 到 30 秒")
        self.seconds = seconds
        self.previous = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self.previous
        if self.previous and elapsed < self.seconds:
            time.sleep(self.seconds - elapsed)
        self.previous = time.monotonic()


def state_value(path: Path, catalog_hash: str) -> dict:
    if path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("schema_version") != 1 or not isinstance(state.get("items"), dict):
            raise StructuredBatchError("續傳狀態檔格式錯誤")
    else:
        state = {"schema_version": 1, "items": {}}
    state["catalog_hash"] = catalog_hash
    return state


def fetch_batch(
    license_source: Path,
    output_dir: Path,
    *,
    max_items: int = 100,
    request_delay: float = 2.0,
    recheck_no_document_days: int = 30,
    fetch: Callable[[Query], bytes] = fetch_xml,
) -> dict:
    if not 1 <= max_items <= 1000:
        raise ValueError("每批數量必須是 1 到 1000")
    if not 1 <= recheck_no_document_days <= 365:
        raise ValueError("無仿單重查天數必須是 1 到 365")
    bundle = official.build_bundle("licenses", license_source.read_bytes(), allow_small=True)
    active = active_catalog(bundle)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "state.json"
    state = state_value(state_path, bundle["content_hash"])
    limiter = RateLimiter(request_delay)
    report = {"attempted": 0, "downloaded": 0, "no_document": 0, "unqueryable": 0}

    recheck_before = datetime.now(timezone.utc) - timedelta(days=recheck_no_document_days)

    def completed_item(item: dict) -> bool:
        if item.get("status") in {"downloaded", "unqueryable"}:
            return True
        if item.get("status") != "no_document":
            return False
        try:
            checked = datetime.fromisoformat(str(item.get("checked_at") or "").replace("Z", "+00:00"))
            return checked >= recheck_before
        except ValueError:
            return False

    completed = {number for number, item in state["items"].items() if completed_item(item)}
    pending = [number for number in sorted(active) if number not in completed]
    for number in pending[:max_items]:
        report["attempted"] += 1
        code = active[number].get("license_code") or license_code(number)
        if not code:
            state["items"][number] = {"status": "unqueryable", "checked_at": datetime.now(timezone.utc).isoformat()}
            report["unqueryable"] += 1
            atomic_json(state_path, state)
            continue
        query = Query(license_code=code)
        try:
            limiter.wait()
            parsed = parse_xml(fetch(query), query)
            documents = [item for item in parsed["documents"] if item["license_no"] == number]
            if not documents:
                raise NoDocumentError("API 未回傳完全相同的藥證字號")
            parsed["documents"] = documents
            parsed["document_count"] = len(documents)
            atomic_json(output_dir / "documents" / f"{code}.json", parsed)
            state["items"][number] = {
                "status": "downloaded",
                "license_code": code,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            report["downloaded"] += 1
        except NoDocumentError:
            state["items"][number] = {
                "status": "no_document",
                "license_code": code,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            report["no_document"] += 1
        except Exception as exc:
            state["items"][number] = {
                "status": "failed",
                "license_code": code,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "error_category": type(exc).__name__,
                "error": str(exc)[:500],
            }
            atomic_json(state_path, state)
            raise StructuredBatchError(f"{number} 下載失敗，已保存續傳狀態") from exc
        atomic_json(state_path, state)

    report["remaining"] = sum(
        1 for number in active
        if state["items"].get(number, {}).get("status") not in {"downloaded", "no_document", "unqueryable"}
    )
    report["complete"] = report["remaining"] == 0
    report["catalog_hash"] = bundle["content_hash"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--license-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--request-delay", type=float, default=2.0)
    parser.add_argument("--recheck-no-document-days", type=int, default=30)
    args = parser.parse_args()
    report = fetch_batch(
        args.license_source,
        args.output_dir,
        max_items=args.max_items,
        request_delay=args.request_delay,
        recheck_no_document_days=args.recheck_no_document_days,
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
