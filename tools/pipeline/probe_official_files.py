#!/usr/bin/env python3
"""Safely sample TFDA label-file links without retaining the linked files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from typing import Callable
import urllib.error
import urllib.parse
import urllib.request


ALLOWED_HOST = "mcp.fda.gov.tw"
MAX_ITEMS = 100
SNIFF_BYTES = 64 * 1024


class FileProbeError(ValueError):
    """The input or an official response is unsafe to inspect."""


class FileProbeAuthorizationError(PermissionError):
    """No external request may start without one-run authorization."""


def checked_url(value: object) -> str:
    raw = str(value or "").strip()
    try:
        url = urllib.parse.urlsplit(raw)
    except ValueError as error:
        raise FileProbeError("官方仿單檔案網址格式錯誤") from error
    if (
        url.scheme != "https"
        or url.hostname != ALLOWED_HOST
        or url.username
        or url.password
        or url.port not in (None, 443)
    ):
        raise FileProbeError("官方仿單檔案必須是 TFDA MCP HTTPS 網址")
    return raw


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_prefix(url: str) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        checked_url(url),
        headers={
            "User-Agent": "TFDA-label-search-file-probe/1.0",
            "Range": f"bytes=0-{SNIFF_BYTES - 1}",
            "Accept": "application/pdf,image/*,text/html;q=0.5,*/*;q=0.1",
        },
    )
    opener = urllib.request.build_opener(OfficialRedirect())
    with opener.open(request, timeout=60) as response:
        final_url = checked_url(response.geturl())
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        prefix = response.read(SNIFF_BYTES)
    if not prefix:
        raise FileProbeError("官方檔案回應為空")
    return prefix, content_type, final_url


def detected_format(prefix: bytes, content_type: str) -> str:
    start = prefix.lstrip()[:32].lower()
    if prefix.startswith(b"%PDF-"):
        return "pdf_header"
    if (
        prefix.startswith(b"\x89PNG\r\n\x1a\n")
        or prefix.startswith(b"\xff\xd8\xff")
        or prefix.startswith((b"GIF87a", b"GIF89a"))
        or prefix.startswith((b"II*\x00", b"MM\x00*"))
        or (prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP")
    ):
        return "image_header"
    if content_type == "text/html" or start.startswith((b"<!doctype html", b"<html")):
        return "html_page"
    return "unknown"


def load_targets(path: Path) -> list[dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FileProbeError(f"無法讀取 release 文件：{error}") from error
    if not isinstance(payload, dict):
        raise FileProbeError("release 文件格式不正確")
    documents = payload.get("documents")
    if payload.get("schema_version") != 1 or not isinstance(documents, list):
        raise FileProbeError("release 文件格式不正確")
    if payload.get("document_count") != len(documents):
        raise FileProbeError("release 文件數量與內容不一致")
    targets = []
    seen = set()
    for document in documents:
        license_no = str(document.get("license_no") or "").strip()
        urls = document.get("pdf_urls")
        if not license_no or not isinstance(urls, list):
            raise FileProbeError("release 含缺少藥證或官方檔案清單的文件")
        for raw_url in urls:
            url = checked_url(raw_url)
            key = (license_no, url)
            if key not in seen:
                seen.add(key)
                targets.append({"license_no": license_no, "url": url})
    return targets


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def probe_official_files(
    documents_path: Path,
    report_path: Path,
    *,
    authorized: bool = False,
    max_items: int = 25,
    request_delay: float = 2.0,
    fetcher: Callable[[str], tuple[bytes, str, str]] = fetch_prefix,
) -> dict:
    if max_items not in range(1, MAX_ITEMS + 1):
        raise FileProbeError(f"抽查數量必須是 1 到 {MAX_ITEMS}")
    if request_delay < 0:
        raise FileProbeError("請求間隔不可為負數")
    all_targets = load_targets(documents_path)
    targets = all_targets[:max_items]
    if targets and not authorized:
        raise FileProbeAuthorizationError(
            f"本輪將讀取最多 {len(targets)} 個 TFDA 官方仿單檔頭；必須另行明確授權"
        )

    results = []
    for index, target in enumerate(targets):
        if index and request_delay:
            time.sleep(request_delay)
        try:
            prefix, content_type, final_url = fetcher(target["url"])
            final_url = checked_url(final_url)
            if not prefix:
                raise FileProbeError("官方檔案回應為空")
            results.append({
                **target,
                "status": "sampled",
                "format": detected_format(prefix[:SNIFF_BYTES], content_type),
                "content_type": str(content_type or "").strip().lower(),
                "final_url": final_url,
                "sampled_bytes": min(len(prefix), SNIFF_BYTES),
            })
        except urllib.error.HTTPError as error:
            results.append({**target, "status": "failed", "error": f"HTTP {error.code}"})
        except (urllib.error.URLError, TimeoutError, OSError, FileProbeError) as error:
            results.append({**target, "status": "failed", "error": type(error).__name__})

    formats = {name: 0 for name in ("pdf_header", "image_header", "html_page", "unknown")}
    for item in results:
        if item["status"] == "sampled":
            formats[item["format"]] += 1
    failed = sum(item["status"] == "failed" for item in results)
    report = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source": str(documents_path),
        "requested_limit": max_items,
        "available_links": len(all_targets),
        "sampled_links": len(results),
        "complete": failed == 0,
        "note": "只檢查最多 64 KiB 檔頭；PDF 標頭不等於已證明整份 PDF 可完整開啟。",
        "summary": {**formats, "failed": failed},
        "results": results,
    }
    atomic_json(report_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=25)
    parser.add_argument("--request-delay", type=float, default=2.0)
    parser.add_argument(
        "--authorization",
        choices=("authorized", "not_authorized"),
        default="not_authorized",
    )
    args = parser.parse_args()
    report = probe_official_files(
        args.documents,
        args.report,
        authorized=args.authorization == "authorized",
        max_items=args.max_items,
        request_delay=args.request_delay,
    )
    print(json.dumps(report, ensure_ascii=False))
    if not report["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
