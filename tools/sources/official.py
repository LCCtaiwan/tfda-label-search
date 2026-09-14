#!/usr/bin/env python3
"""Download, validate and normalize official TFDA/NHIA datasets."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
SOURCES_PATH = HERE / "official_sources.json"
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_UNCOMPRESSED = 512 * 1024 * 1024
ALLOWED_HOSTS = {"data.fda.gov.tw", "info.nhi.gov.tw"}
FULL_LICENSE_RE = re.compile(r"(?:衛署|衛部|內衛)[^\s,，;；、]{1,12}字第(?:R?\d{5,6})號")

class SourceError(ValueError):
    pass

def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())

def checked_url(value: str) -> str:
    url = urllib.parse.urlsplit(value)
    if url.scheme != "https" or url.hostname not in ALLOWED_HOSTS or url.username or url.password or url.port not in (None, 443):
        raise SourceError("來源必須是指定的 TFDA 或健保署 HTTPS 網址")
    return value

class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        checked_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def download(url: str, *, attempts: int = 3) -> bytes:
    if attempts not in range(1, 6):
        raise SourceError("下載重試次數必須是 1 到 5")
    request = urllib.request.Request(checked_url(url), headers={"User-Agent": "TFDA-label-search-updater/1.0"})
    opener = urllib.request.build_opener(OfficialRedirect())
    for attempt in range(attempts):
        try:
            with opener.open(request, timeout=240) as response:
                checked_url(response.geturl())
                data = response.read(MAX_DOWNLOAD + 1)
            if not data or len(data) > MAX_DOWNLOAD:
                raise SourceError("官方下載為空或超過 256 MiB")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt + 1 == attempts:
                raise SourceError(f"官方下載失敗（HTTP {exc.code}）") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt + 1 == attempts:
                raise SourceError("官方下載連線失敗") from exc
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")

def decode_rows(data: bytes, source_format: str) -> list[dict]:
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir() and entry.filename.lower().endswith((".json", ".csv"))]
            if len(entries) != 1 or entries[0].file_size > MAX_UNCOMPRESSED:
                raise SourceError("壓縮檔必須只有一個 JSON/CSV，且解壓後不超過 512 MiB")
            data = archive.read(entries[0])
            source_format = "csv" if entries[0].filename.lower().endswith(".csv") else "json"
    text = data.decode("utf-8-sig")
    if source_format == "json":
        value = json.loads(text)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise SourceError("官方 JSON 必須是物件陣列")
        return value
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise SourceError("官方 CSV 沒有資料")
    return rows

def parse_date(value: object) -> str:
    raw = clean(value)
    if not raw:
        return ""
    match = re.fullmatch(r"(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})", raw)
    if not match:
        return ""
    year, month, day = map(int, match.groups())
    if year < 1911:
        year += 1911
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""

def official_license_id(url: object) -> str:
    try:
        parsed = urllib.parse.urlsplit(clean(url))
        values = urllib.parse.parse_qs(parsed.query).get("licId", [])
        if parsed.scheme == "https" and parsed.hostname == "lmspiq.fda.gov.tw" and len(values) == 1 and re.fullmatch(r"\d{2}(?:\d{6}|R\d{5})", values[0]):
            return values[0]
    except ValueError:
        pass
    return ""

def extract_licenses(value: object) -> list[dict]:
    raw = clean(value)
    matches = list(dict.fromkeys(FULL_LICENSE_RE.findall(raw)))
    if not matches and raw and len(raw) <= 80:
        matches = [raw]
    return [{"raw_license_no": item, "license_no": item if FULL_LICENSE_RE.fullmatch(item) else ""} for item in matches]

def source_key(row: dict) -> str:
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

def normalize(source: str, rows: list[dict]) -> tuple[str, list[dict]]:
    if source == "licenses":
        return "expected_licenses", rows
    if source == "pdf_catalog":
        return "pdf_catalog", rows
    if source == "ingredients":
        positions: dict[str, int] = {}
        result = []
        for row in rows:
            license_no = clean(row.get("許可證字號")); positions[license_no] = positions.get(license_no, 0) + 1
            result.append({"license_no": license_no, "position": positions[license_no], "label_text": clean(row.get("處方標示")),
                "ingredient_name": clean(row.get("成分名稱")), "ingredient_code": clean(row.get("成分代碼")),
                "amount_description": clean(row.get("含量描述")), "amount": clean(row.get("含量")), "unit": clean(row.get("含量單位")), "source_record": row})
        return "ingredients", result
    if source == "nhi_items":
        result = []
        for row in rows:
            result.append({"nhi_code": clean(row.get("藥品代號")), "drug_name_zh": clean(row.get("藥品中文名稱")),
                "drug_name_en": clean(row.get("藥品英文名稱")), "ingredient_text": clean(row.get("成分")),
                "specification": " ".join(filter(None, [clean(row.get("規格量")), clean(row.get("規格單位"))])),
                "price": clean(row.get("支付價")), "effective_from": parse_date(row.get("有效起日")),
                "effective_until": parse_date(row.get("有效迄日")), "company": clean(row.get("藥商")),
                "dosage_form": clean(row.get("劑型")), "atc_code": clean(row.get("ATC代碼")),
                "benefit_chapter": clean(row.get("給付規定章節")), "item_url": clean(row.get("藥品代碼超連結")),
                "rule_url": clean(row.get("給付規定章節連結")), "official_license_id": official_license_id(row.get("藥品代碼超連結")), "source_record": row})
        return "nhi_items", result
    mapping = {
        "recalls": ("recall", "日期", "產品", "回收分級", "原因", "許可證字號", "文號"),
        "safety_alerts": ("safety_alert", "發布日期", "藥品成分", "", "TFDA風險溝通說明", "藥品名稱及許可證字號", ""),
        "risk_management": ("risk_management", "", "中文品名", "須執行風險管理計畫", "申請商", "許可證字號", ""),
        "shortage_with_alternative": ("shortage_with_alternative", "公告更新時間", "中文品名", "供應狀態", "", "許可證字號", "編號"),
        "shortage_without_alternative": ("shortage_without_alternative", "公告更新時間", "中文品名", "供應狀態", "", "許可證字號", "編號"),
    }
    event_type, date_field, title_field, status_field, detail_field, license_field, key_field = mapping[source]
    result = []
    for row in rows:
        if clean(row.get(key_field)) == "沒有資料" or clean(row.get("編號")) == "沒有資料":
            continue
        result.append({"event_type": event_type, "source_key": clean(row.get(key_field)) or source_key(row),
            "published_on": parse_date(row.get(date_field)), "title": clean(row.get(title_field)),
            "status": clean(row.get(status_field)), "detail": clean(row.get(detail_field)),
            "source_url": load_sources()[source]["url"], "licenses": extract_licenses(row.get(license_field)), "source_record": row})
    return "events", result

def load_sources() -> dict:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))

def build_bundle(source: str, data: bytes, *, allow_small: bool = False, retrieved_at: str | None = None) -> dict:
    sources = load_sources()
    if source not in sources:
        raise SourceError("未知官方資料源")
    spec = sources[source]; rows = decode_rows(data, spec["format"])
    if rows:
        missing = set(spec["required_fields"]) - set(rows[0])
        if missing:
            raise SourceError("官方欄位異動，缺少：" + "、".join(sorted(missing)))
    if not allow_small and len(rows) < spec["minimum_records"]:
        raise SourceError(f"官方資料筆數過少：{len(rows)} < {spec['minimum_records']}")
    kind, records = normalize(source, rows)
    keys = sorted({key for row in rows for key in row})
    return {"schema_version": 1, "source_name": source, "kind": kind,
        "source": {"provider": spec["provider"], "url": spec["url"], "info_id": spec.get("info_id"), "resource_id": spec.get("resource_id")},
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        "content_hash": hashlib.sha256(data).hexdigest(), "schema_hash": hashlib.sha256("\n".join(keys).encode()).hexdigest(),
        "source_record_count": len(rows), "normalized_record_count": len(records), "records": records}

def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write("\n"); temporary = Path(handle.name)
    temporary.replace(path)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=sorted(load_sources()), required=True)
    parser.add_argument("--input", type=Path, help="讀取已下載檔案；省略時才連官方網址")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-small-fixture", action="store_true", help="只供測試資料，不得用於正式更新")
    args = parser.parse_args(); spec = load_sources()[args.source]
    data = args.input.read_bytes() if args.input else download(spec["url"])
    atomic_write(args.output, build_bundle(args.source, data, allow_small=args.allow_small_fixture))

if __name__ == "__main__":
    main()

