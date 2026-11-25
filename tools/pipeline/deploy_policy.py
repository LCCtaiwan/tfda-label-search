"""Pin refresh provenance and require review unless the last approved app matches."""

import argparse
import json
from pathlib import Path
import re


def sha(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{40}", value):
        raise ValueError("Expected a full immutable commit SHA")
    return value


def selected_refs(event: dict, provenance: dict | None) -> tuple[str, str]:
    run = event.get("workflow_run")
    if run is None:
        inputs = event.get("inputs", {})
        refs = (inputs.get("app_ref", "main"), inputs.get("data_ref", "data-state"))
        if any(not isinstance(ref, str) or not ref.strip() or "\n" in ref or "\r" in ref for ref in refs):
            raise ValueError("Invalid manual ref")
        return refs
    repository = event["repository"]
    if (
        run.get("event") != "schedule"
        or run.get("conclusion") != "success"
        or run.get("head_repository", {}).get("full_name") != repository["full_name"]
        or run.get("head_branch") != repository["default_branch"]
        or not isinstance(provenance, dict)
        or provenance.get("schema_version") != 1
        or provenance.get("event") != "schedule"
        or provenance.get("run_id") != str(run["id"])
        or provenance.get("app_sha") != run.get("head_sha")
    ):
        raise ValueError("Scheduled refresh provenance does not match the successful upstream run")
    return sha(provenance["app_sha"]), sha(provenance.get("data_sha"))


def automatic_allowed(event: dict, provenance: dict | None, approved: dict | None, app_sha: str, data_sha: str) -> bool:
    app_ref, data_ref = selected_refs(event, provenance)
    if "workflow_run" not in event:
        return False
    if (sha(app_sha), sha(data_sha)) != (app_ref, data_ref):
        raise ValueError("Checked-out commits differ from refresh provenance")
    return bool(
        isinstance(approved, dict)
        and approved.get("schema_version") == 1
        and approved.get("app_sha") == app_sha
        and approved.get("environment") == "github-pages"
        and str(approved.get("deployment_run_id", "")).isdigit()
        and approved.get("repository") == event["repository"]["full_name"]
    )


def optional_json(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # Missing/corrupt approval evidence always requires a reviewer.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--approved-record", type=Path)
    parser.add_argument("--app-sha")
    parser.add_argument("--data-sha")
    args = parser.parse_args()
    event = json.loads(args.event.read_text(encoding="utf-8"))
    provenance = optional_json(args.provenance)
    if args.app_sha:
        automatic = automatic_allowed(event, provenance, optional_json(args.approved_record), args.app_sha, args.data_sha)
        print("auto_deploy=" + str(automatic).lower())
    else:
        app_ref, data_ref = selected_refs(event, provenance)
        print("app_ref=" + app_ref)
        print("data_ref=" + data_ref)
