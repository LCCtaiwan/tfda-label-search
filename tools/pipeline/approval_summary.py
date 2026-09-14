#!/usr/bin/env python3
"""Build a human-readable, cross-checked supervisor deployment summary."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import tempfile


SOURCE_NAMES = {
    "licenses",
    "ingredients",
    "pdf_catalog",
    "recalls",
    "safety_alerts",
    "risk_management",
    "shortage_with_alternative",
    "shortage_without_alternative",
    "nhi_items",
}
REQUIRED_PUBLICATION_CHECKS = {
    "policy_review_current",
    "official_open_data_verified",
    "official_dataset_scope_verified",
    "structured_plain_text_only",
    "visible_provider_attribution",
    "visible_license_notice",
    "visible_disclaimer",
}
THIRD_PARTY_CHECKS = {"third_party_not_included", "third_party_consent_verified"}


class ApprovalSummaryError(ValueError):
    """The candidate evidence is incomplete, inconsistent, or unsafe to approve."""


def load_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ApprovalSummaryError(f"無法讀取{label}：{error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ApprovalSummaryError(f"{label}不是 schema_version 1 物件")
    return value


def integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ApprovalSummaryError(f"{label}必須是非負整數")
    return value


def number(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ApprovalSummaryError(f"{label}必須是數字")
    return float(value)


def exact_sha(value: object, label: str) -> str:
    raw = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{40}", raw):
        raise ApprovalSummaryError(f"{label}必須是完整 40 碼 Git SHA")
    return raw


def inline(value: object) -> str:
    safe = re.sub(r"[\r\n]+", " ", str(value or "").strip())
    safe = safe.replace("`", "ˋ").replace("|", "\\|")
    return f"`{safe}`"


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(value)
        temporary = Path(handle.name)
    temporary.replace(path)


def build_approval_summary(
    manifest_path: Path,
    coverage_path: Path,
    data_state_path: Path,
    preflight_path: Path,
    synonyms_path: Path,
    *,
    min_structured_coverage: float = 0.98,
    max_age_days: int = 14,
    max_lag_days: int = 14,
) -> str:
    if not 0 <= min_structured_coverage <= 1:
        raise ApprovalSummaryError("涵蓋率門檻必須介於 0 與 1")
    if max_age_days < 0 or max_lag_days < 0:
        raise ApprovalSummaryError("資料年齡與增量落後門檻不可為負數")

    manifest = load_object(manifest_path, "release manifest")
    coverage = load_object(coverage_path, "coverage")
    data_state = load_object(data_state_path, "data-state 預檢")
    preflight = load_object(preflight_path, "publication preflight")
    synonyms = load_object(synonyms_path, "同義詞")

    if manifest.get("ready") is not True or preflight.get("ready") is not True:
        raise ApprovalSummaryError("release 或 publication preflight 尚未通過")
    if not str(manifest.get("release_id") or "").strip():
        raise ApprovalSummaryError("release manifest 缺少 release id")
    if not str(manifest.get("official_snapshot_id") or "").strip():
        raise ApprovalSummaryError("release manifest 缺少官方 snapshot id")
    if not str(manifest.get("data_retrieved_at") or "").strip():
        raise ApprovalSummaryError("release manifest 缺少官方資料日期")
    if data_state.get("complete") is not True:
        raise ApprovalSummaryError("data-state 尚未完成初次檢查")
    if data_state.get("incremental_initialized") is not True:
        raise ApprovalSummaryError("data-state 尚未建立增量游標")

    manifest_coverage = manifest.get("coverage")
    public_coverage = {key: value for key, value in coverage.items() if key != "schema_version"}
    if not isinstance(manifest_coverage, dict) or manifest_coverage != public_coverage:
        raise ApprovalSummaryError("coverage 與 release manifest 不一致")
    if manifest.get("official_snapshot_id") != data_state.get("official_snapshot_id"):
        raise ApprovalSummaryError("release 與 data-state 的官方 snapshot 不一致")

    app_sha = exact_sha(manifest.get("app_revision"), "app revision")
    data_sha = exact_sha(manifest.get("data_revision"), "data revision")
    source_hashes = manifest.get("source_hashes")
    if not isinstance(source_hashes, dict) or set(source_hashes) != SOURCE_NAMES:
        raise ApprovalSummaryError("release 必須保留完整九來源雜湊")
    if any(not re.fullmatch(r"[a-f0-9]{64}", str(value or "")) for value in source_hashes.values()):
        raise ApprovalSummaryError("九來源雜湊格式錯誤")

    active = integer(coverage.get("active_licenses"), "有效藥證數")
    structured = integer(coverage.get("structured_licenses"), "結構化仿單數")
    metadata_only = integer(coverage.get("metadata_only_licenses"), "無結構化文字藥證數")
    with_files = integer(
        coverage.get("metadata_only_with_official_files"), "只有官方檔案的藥證數"
    )
    without_files = integer(
        coverage.get("metadata_only_without_official_files"), "文字與檔案皆無的藥證數"
    )
    structured_coverage = number(coverage.get("structured_coverage"), "結構化涵蓋率")
    if not 0 <= structured_coverage <= 1:
        raise ApprovalSummaryError("結構化涵蓋率必須介於 0 與 1")
    if metadata_only != with_files + without_files or structured + metadata_only != active:
        raise ApprovalSummaryError("涵蓋分類加總不等於有效藥證數")
    if active == 0 or abs(structured / active - structured_coverage) > 1e-12:
        raise ApprovalSummaryError("結構化涵蓋率與藥證數不一致")
    if structured_coverage < min_structured_coverage:
        raise ApprovalSummaryError("結構化涵蓋率低於主管核准門檻")
    state_coverage = number(data_state.get("structured_coverage"), "data-state 結構化涵蓋率")
    if (
        data_state.get("active_licenses") != active
        or data_state.get("downloaded_licenses") != structured
        or abs(state_coverage - structured_coverage) > 1e-12
    ):
        raise ApprovalSummaryError("data-state 與 release 涵蓋數量不一致")

    snapshot_age = integer(data_state.get("official_snapshot_age_days"), "官方 snapshot 年齡")
    lag_days = integer(data_state.get("incremental_lag_days"), "增量落後天數")
    manifest_age = integer(manifest.get("official_snapshot_age_days"), "release snapshot 年齡")
    if manifest_age != snapshot_age:
        raise ApprovalSummaryError("release 與 data-state 的 snapshot 年齡不一致")
    if snapshot_age > max_age_days or lag_days > max_lag_days:
        raise ApprovalSummaryError("官方資料年齡或增量落後超過主管核准門檻")

    checks = preflight.get("checks")
    if not isinstance(checks, list) or any(not isinstance(item, str) for item in checks):
        raise ApprovalSummaryError("publication preflight 必須有完整 8 項檢查")
    check_set = set(checks)
    if (
        len(checks) != 8
        or not REQUIRED_PUBLICATION_CHECKS.issubset(check_set)
        or len(check_set & THIRD_PARTY_CHECKS) != 1
        or check_set - REQUIRED_PUBLICATION_CHECKS - THIRD_PARTY_CHECKS
    ):
        raise ApprovalSummaryError("publication preflight 必須有完整 8 項檢查")
    entries = synonyms.get("entries")
    if not isinstance(entries, list):
        raise ApprovalSummaryError("同義詞 entries 必須是清單")
    reviewed_terms = 0
    for entry in entries:
        terms = entry.get("terms") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or entry.get("reviewed") is not True
            or not isinstance(terms, list)
            or len(terms) < 2
            or any(not isinstance(term, str) or not term.strip() for term in terms)
            or not str(entry.get("reviewer") or "").strip()
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry.get("reviewed_at") or ""))
        ):
            raise ApprovalSummaryError("公開同義詞含未核准或格式錯誤的詞組")
        reviewed_terms += len(terms)

    linkage = coverage.get("nhi_linkage")
    if not isinstance(linkage, dict):
        raise ApprovalSummaryError("coverage 缺少健保連接報告")
    linkage_counts = {
        key: integer(linkage.get(key), f"健保連接 {key}")
        for key in ("matched", "unresolved", "ambiguous", "missing_official_id")
    }
    warnings = []
    if without_files:
        warnings.append(f"有 {without_files} 張有效藥證沒有結構化文字，也沒有官方檔案連結。")
    unresolved = linkage_counts["unresolved"] + linkage_counts["ambiguous"]
    if unresolved:
        warnings.append(f"有 {unresolved} 筆健保品項無法唯一連到有效藥證。")
    if not entries:
        warnings.append("目前沒有正式核准的人工同義詞；基本關鍵字搜尋仍可使用。")
    warning_lines = "\n".join(f"- 注意：{item}" for item in warnings) or "- 無額外警告。"

    summary = f"""# TFDA Pages 主管核准摘要

這不是自動核准。請同時下載本次 `release-audit` 附件，核對五份原始證據。

| 項目 | 本次候選版 |
|---|---|
| Release | {inline(manifest.get('release_id'))} |
| 程式 commit | {inline(app_sha)} |
| 資料 commit | {inline(data_sha)} |
| 官方 snapshot | {inline(manifest.get('official_snapshot_id'))} |
| 官方資料日期 | {inline(manifest.get('data_retrieved_at'))} |
| Snapshot 年齡 | {snapshot_age} 天（門檻 ≤ {max_age_days}） |
| 增量落後 | {lag_days} 天（門檻 ≤ {max_lag_days}） |
| 有效藥證 | {active} |
| 有結構化仿單文字 | {structured}（{structured_coverage:.2%}，門檻 ≥ {min_structured_coverage:.0%}） |
| 只有官方檔案連結 | {with_files} |
| 文字與官方檔案皆無 | {without_files} |
| 健保連接 | 成功 {linkage_counts['matched']}／找不到 {linkage_counts['unresolved']}／不唯一 {linkage_counts['ambiguous']}／缺官方藥證碼 {linkage_counts['missing_official_id']} |
| 正式同義詞 | {len(entries)} 組、{reviewed_terms} 詞 |
| 公開發布檢查 | {len(checks)}／8 通過 |
| 九來源雜湊 | 9／9 完整 |

## 需要主管特別注意

{warning_lines}

## 人工決定

- 若數字與預期不同、原始附件看不懂或來源異常，請按 **Reject**；舊網站會保持不變。
- 只有確認本次程式 commit、資料 commit、同義詞與來源都正確，才按 **Approve and deploy**。
"""
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--data-state", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--synonyms", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-structured-coverage", type=float, default=0.98)
    parser.add_argument("--max-age-days", type=int, default=14)
    parser.add_argument("--max-lag-days", type=int, default=14)
    args = parser.parse_args()
    summary = build_approval_summary(
        args.manifest,
        args.coverage,
        args.data_state,
        args.preflight,
        args.synonyms,
        min_structured_coverage=args.min_structured_coverage,
        max_age_days=args.max_age_days,
        max_lag_days=args.max_lag_days,
    )
    atomic_text(args.output, summary)
    print(summary)


if __name__ == "__main__":
    main()
