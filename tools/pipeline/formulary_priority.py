"""Use a private formulary in memory only; emit aggregate priority counts only."""

from collections import defaultdict
import csv
import io
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit
from urllib.request import urlopen

from tools.sources import official


MAX_CSV_BYTES = 4 * 1024 * 1024
GENERIC_TOKENS = {
    "tablet", "tablets", "capsule", "capsules", "injection", "solution",
    "cream", "oral", "sodium", "hydrochloride", "extended", "release",
}


def english_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9]{2,}", unicodedata.normalize("NFKC", value).lower())) - GENERIC_TOKENS


def atc_codes(value: str) -> set[str]:
    return set(re.findall(r"\b[A-Z][0-9]{2}[A-Z]{2}[0-9]{2}\b", value.upper()))


def download_csv(url: str) -> bytes:
    if urlsplit(url).scheme != "https":
        raise ValueError("HTTPS required")
    with urlopen(url, timeout=30) as response:
        if urlsplit(response.geturl()).scheme != "https":
            raise ValueError("HTTPS required")
        payload = response.read(MAX_CSV_BYTES + 1)
    if len(payload) > MAX_CSV_BYTES:
        raise ValueError("CSV too large")
    return payload


def prioritize(pending: list[str], active: dict, source_dir: Path, payload: bytes) -> tuple[list[str], dict]:
    rows = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if not {"藥名", "ATC碼", "狀態"}.issubset(rows.fieldnames or []):
        raise ValueError("CSV headers missing")
    hospital = defaultdict(set)
    for row in rows:
        if str(row.get("狀態") or "").strip() == "停用":
            continue
        for code in atc_codes(str(row.get("ATC碼") or "")):
            hospital[code].update(english_tokens(str(row.get("藥名") or "")))

    # Both enrichment sources are already validated official snapshot files.
    nhi = official.build_bundle("nhi_items", (source_dir / "nhi_items.raw").read_bytes(), allow_small=True)
    ingredients = official.build_bundle("ingredients", (source_dir / "ingredients.raw").read_bytes(), allow_small=True)
    licenses = official.build_bundle("licenses", (source_dir / "licenses.raw").read_bytes(), allow_small=True)
    codes = defaultdict(set)
    tokens = defaultdict(set)
    by_code = {item["license_code"]: number for number, item in active.items() if item.get("license_code")}
    for number, item in active.items():
        tokens[number].update(english_tokens(item.get("drug_name_en", "")))
    for item in licenses["records"]:
        number = item.get("許可證字號")
        codes[number].update(atc_codes(str(item.get("ATC代碼") or item.get("ATC碼") or "")))
    for item in ingredients["records"]:
        tokens[item["license_no"]].update(english_tokens(item["ingredient_name"]))
    for item in nhi["records"]:
        number = by_code.get(item["official_license_id"])
        if number:
            codes[number].update(atc_codes(item["atc_code"]))
            tokens[number].update(english_tokens(item["drug_name_en"] + " " + item["ingredient_text"]))

    tiers = {1: [], 2: [], 3: []}
    for number in pending:
        matching = codes[number] & hospital.keys()
        tier = 1 if any(tokens[number] & hospital[code] for code in matching) else 2 if matching else 3
        tiers[tier].append(number)
    return [number for tier in tiers.values() for number in tier], {
        f"tier{tier}": len(numbers) for tier, numbers in tiers.items()
    }


def optional_priority(pending: list[str], active: dict, source_dir: Path, *, download=download_csv) -> list[str]:
    url = os.environ.get("FORMULARY_CSV_URL", "").strip()
    if not url:
        print("Warning: formulary secret unset; using existing order.")
        return pending
    try:
        ordered, counts = prioritize(pending, active, source_dir, download(url))
    except Exception:
        # Never include exception text: URLs, HTTP bodies and CSV rows are private.
        print("Warning: formulary unavailable or invalid; using existing order.")
        return pending
    for tier, count in counts.items():
        print(f"priority {tier}: {count}")
    return ordered
