#!/usr/bin/env python3
"""Fail closed when publication evidence or visible attribution is incomplete."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.pipeline.static_release import StaticReleaseError, atomic_json


ALLOWED_EVIDENCE_HOSTS = {"data.gov.tw", "www.fda.gov.tw", "mcp.fda.gov.tw"}
REQUIRED_OPEN_DATA_EVIDENCE = {
    "https://data.gov.tw/dataset/9122",
    "https://data.gov.tw/dataset/23715",
    "https://www.fda.gov.tw/Tc/opendata.aspx",
}
REQUIRED_PUBLISHED_DATASETS = {
    "TFDA InfoId 34",
    "TFDA InfoId 36",
    "TFDA InfoId 39",
    "TFDA InfoId 43",
    "TFDA InfoId 53",
    "TFDA InfoId 54",
    "TFDA InfoId 104",
    "TFDA InfoId 105",
    "NHIA A21030000I-E41001-001",
}
REQUIRED_EXCLUSIONS = {"embedded_images", "pdf_mirrors", "agency_logos"}
POLICY_MAX_AGE_DAYS = 366
VISIBLE_NOTICES = (
    "衛生福利部食品藥物管理署",
    "衛生福利部中央健康保險署",
    "政府資料開放授權條款-第1版",
    "https://data.gov.tw/license",
    "本網站不是食藥署官方網站",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_urls(values: object, field: str) -> set[str]:
    if not isinstance(values, list) or not values:
        raise StaticReleaseError(f"{field} 必須列出官方 HTTPS 證據")
    result = set()
    for value in values:
        parsed = urlparse(str(value))
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_EVIDENCE_HOSTS:
            raise StaticReleaseError(f"{field} 含非官方 HTTPS 網址：{value}")
        result.add(str(value).rstrip("/"))
    return result


def checked_relative_file(value: object, project_root: Path, field: str) -> Path:
    relative = Path(str(value or ""))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise StaticReleaseError(f"{field} 路徑不安全")
    target = project_root / relative
    if not target.is_file():
        raise StaticReleaseError(f"{field} 找不到檔案：{relative}")
    return target


def validate_policy(policy: dict, project_root: Path) -> list[str]:
    if policy.get("schema_version") != 1:
        raise StaticReleaseError("publication policy schema_version 必須是 1")
    try:
        reviewed_at = date.fromisoformat(str(policy.get("reviewed_at") or ""))
    except ValueError as error:
        raise StaticReleaseError("publication policy reviewed_at 必須是 YYYY-MM-DD") from error
    age_days = (datetime.now(timezone.utc).date() - reviewed_at).days
    if age_days < -1 or age_days > POLICY_MAX_AGE_DAYS:
        raise StaticReleaseError("公開發布依據已超過一年，必須重新核對官方條款")

    open_data = policy.get("official_open_data")
    if not isinstance(open_data, dict) or open_data.get("status") != "verified":
        raise StaticReleaseError("官方開放資料授權證據尚未確認")
    if open_data.get("license_name") != "政府資料開放授權條款-第1版":
        raise StaticReleaseError("官方開放資料授權名稱不符")
    if open_data.get("license_url") != "https://data.gov.tw/license":
        raise StaticReleaseError("官方開放資料授權網址不符")
    evidence = checked_urls(open_data.get("evidence_urls"), "official_open_data.evidence_urls")
    if not REQUIRED_OPEN_DATA_EVIDENCE.issubset(evidence):
        raise StaticReleaseError("官方開放資料證據不完整")
    published_datasets = open_data.get("published_datasets")
    if not isinstance(published_datasets, list):
        raise StaticReleaseError("official_open_data.published_datasets 必須是清單")
    if (
        not all(isinstance(item, str) for item in published_datasets)
        or len(published_datasets) != len(REQUIRED_PUBLISHED_DATASETS)
        or set(published_datasets) != REQUIRED_PUBLISHED_DATASETS
    ):
        raise StaticReleaseError("正式發布的官方資料集清單不完整或含未審查項目")

    labels = policy.get("structured_labels")
    if not isinstance(labels, dict) or labels.get("status") != "verified_with_limitations":
        raise StaticReleaseError("結構化電子仿單公開範圍尚未確認")
    checked_urls(labels.get("evidence_urls"), "structured_labels.evidence_urls")
    if labels.get("published_content") != ["plain_text"]:
        raise StaticReleaseError("正式網站只允許發布結構化仿單純文字")
    exclusions = set(labels.get("excluded_content") or [])
    if not REQUIRED_EXCLUSIONS.issubset(exclusions):
        raise StaticReleaseError("結構化仿單排除項目不完整")

    third_party = policy.get("third_party_code")
    if not isinstance(third_party, dict):
        raise StaticReleaseError("缺少第三方程式使用狀態")
    status = third_party.get("status")
    if third_party.get("source_url") != "https://github.com/liangRXdev/TFDA-drug-info-search":
        raise StaticReleaseError("第三方專案來源網址不符")
    copied_files = third_party.get("copied_files")
    if not isinstance(copied_files, list):
        raise StaticReleaseError("third_party_code.copied_files 必須是清單")
    if status == "not_included":
        if copied_files:
            raise StaticReleaseError("標示未使用第三方程式，卻列有複製檔案")
    elif status == "consent_verified":
        checked_relative_file(
            third_party.get("consent_record"), project_root, "第三方同意紀錄"
        )
        if not copied_files:
            raise StaticReleaseError("標示使用第三方程式，卻沒有列出複製檔案")
        for copied_file in copied_files:
            checked_relative_file(copied_file, project_root, "第三方複製檔案")
        if not str(third_party.get("required_attribution") or "").strip():
            raise StaticReleaseError("缺少第三方必要署名")
    else:
        raise StaticReleaseError("第三方程式狀態必須是 not_included 或 consent_verified")

    return [
        "policy_review_current",
        "official_open_data_verified",
        "official_dataset_scope_verified",
        "structured_plain_text_only",
        f"third_party_{status}",
    ]


def validate_visible_attribution(site_root: Path) -> list[str]:
    index_path = site_root / "index.html"
    if not index_path.is_file():
        raise StaticReleaseError("候選網站缺少 index.html")
    html = index_path.read_text(encoding="utf-8")
    missing = [notice for notice in VISIBLE_NOTICES if notice not in html]
    if missing:
        raise StaticReleaseError(f"候選網站缺少公開署名或聲明：{'、'.join(missing)}")
    return ["visible_provider_attribution", "visible_license_notice", "visible_disclaimer"]


def run_preflight(policy_path: Path, site_root: Path, project_root: Path) -> dict:
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StaticReleaseError(f"無法讀取 publication policy：{error}") from error
    checks = validate_policy(policy, project_root.resolve())
    checks.extend(validate_visible_attribution(site_root.resolve()))
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ready": True,
        "checks": checks,
        "policy_sha256": sha256(policy_path),
        "site_index_sha256": sha256(site_root / "index.html"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--site-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_preflight(args.policy, args.site_root, args.project_root)
    atomic_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
