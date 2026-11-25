from copy import deepcopy
import unittest

from tools.pipeline.deploy_policy import automatic_allowed, selected_refs


class DeployPolicyTests(unittest.TestCase):
    def evidence(self):
        event = {
            "repository": {"full_name": "owner/repo", "default_branch": "main"},
            "workflow_run": {"id": 123, "event": "schedule", "conclusion": "success", "head_sha": "a" * 40, "head_branch": "main", "head_repository": {"full_name": "owner/repo"}},
        }
        provenance = {"schema_version": 1, "event": "schedule", "run_id": "123", "app_sha": "a" * 40, "data_sha": "b" * 40}
        approved = {"schema_version": 1, "app_sha": "a" * 40, "environment": "github-pages", "repository": "owner/repo", "deployment_run_id": "100"}
        return event, provenance, approved

    def test_only_same_app_successful_schedule_can_auto_deploy(self):
        event, provenance, approved = self.evidence()
        self.assertTrue(automatic_allowed(event, provenance, approved, "a" * 40, "b" * 40))
        for record in [None, {}, {**approved, "app_sha": "c" * 40}, {**approved, "environment": "github-pages-auto"}, {**approved, "repository": "other/repo"}]:
            self.assertFalse(automatic_allowed(event, provenance, record, "a" * 40, "b" * 40))
        manual = {"inputs": {"app_ref": "main", "data_ref": "data-state"}}
        self.assertEqual(selected_refs(manual, None), ("main", "data-state"))
        self.assertFalse(automatic_allowed(manual, None, approved, "a" * 40, "b" * 40))

    def test_failed_manual_fork_or_nondefault_upstream_is_rejected(self):
        event, provenance, _ = self.evidence()
        for field, value in [("event", "workflow_dispatch"), ("conclusion", "failure"), ("head_repository", {"full_name": "fork/repo"}), ("head_branch", "unreviewed")]:
            candidate = deepcopy(event)
            candidate["workflow_run"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                selected_refs(candidate, provenance)

    def test_missing_tampered_or_mismatched_revision_evidence_is_rejected(self):
        event, provenance, approved = self.evidence()
        for record in [None, {}, {**provenance, "run_id": "999"}, {**provenance, "app_sha": "c" * 40}, {**provenance, "data_sha": "main"}]:
            with self.subTest(record=record), self.assertRaises(ValueError):
                selected_refs(event, record)
        with self.assertRaises(ValueError):
            automatic_allowed(event, provenance, approved, "a" * 40, "c" * 40)

    def test_output_injection_in_manual_refs_is_rejected(self):
        with self.assertRaises(ValueError):
            selected_refs({"inputs": {"app_ref": "main\nauto_deploy=true"}}, None)
