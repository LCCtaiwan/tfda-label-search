from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkflowGuardTests(unittest.TestCase):
    def test_api_authorization_guard_runs_before_official_download(self):
        workflow = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            workflow.index("TFDA_API_CALLS_AUTHORIZED"),
            workflow.index("official_snapshot.py"),
        )
        self.assertIn("inputs.authorization_ack != true", workflow)
        self.assertRegex(
            workflow,
            r"max_items:\n(?:.*\n){0,4}\s+default: \"25\"",
        )
        self.assertIn("sync_structured.py", workflow)
        self.assertIn("--max-update-windows", workflow)
        self.assertLess(
            workflow.index("validate_official_snapshot.py"),
            workflow.index("sync_structured.py"),
        )
        self.assertLess(
            workflow.index("sync_structured.py"),
            workflow.index("Commit the complete batch atomically"),
        )

    def test_nine_official_sources_are_reused_by_default_after_initialization(self):
        workflow = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            workflow,
            r"official_source_mode:\n(?:.*\n){0,4}\s+default: \"reuse_existing\"",
        )
        self.assertIn("id: data_branch", workflow)
        self.assertIn("initialized=false", workflow)
        self.assertIn(
            "steps.data_branch.outputs.initialized != 'true' && inputs.official_source_mode != 'refresh_all_nine'",
            workflow,
        )
        self.assertGreaterEqual(
            workflow.count("if: inputs.official_source_mode == 'refresh_all_nine'"),
            2,
        )

    def test_publication_guard_and_preflight_run_before_pages_upload(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("SUPERVISOR_APPROVAL_CONFIGURED == 'true'", workflow)
        self.assertIn("PUBLICATION_AUTHORIZED == 'true'", workflow)
        self.assertIn("${{ runner.temp }}/publication-preflight.json", workflow)
        self.assertLess(
            workflow.index("release_preflight.py"),
            workflow.index("actions/upload-pages-artifact"),
        )
        self.assertIn("ref: ${{ inputs.app_ref }}", workflow)
        self.assertIn("ref: ${{ inputs.data_ref }}", workflow)
        self.assertIn("--app-revision \"$APP_SHA\"", workflow)
        self.assertIn("--data-revision \"$DATA_SHA\"", workflow)
        self.assertIn("--source-manifest state/official/current/manifest.json", workflow)
        self.assertIn("--require-incremental", workflow)
        self.assertIn("--max-incremental-lag-days 14", workflow)
        self.assertIn('--expected-app-sha "${{ needs.build.outputs.app_sha }}"', workflow)
        self.assertIn('--expected-data-sha "${{ needs.build.outputs.data_sha }}"', workflow)
        self.assertGreater(
            workflow.index("verify-deployed.mjs"),
            workflow.index("actions/deploy-pages"),
        )
        smoke = workflow.split("  smoke-test:", 1)[1]
        self.assertIn("ref: ${{ needs.build.outputs.app_sha }}", smoke)

    def test_all_official_actions_are_pinned_to_full_commits(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text(encoding="utf-8")
            actions = re.findall(r"uses:\s+(actions/[^@\s]+)@([^\s#]+)", workflow)
            self.assertTrue(actions, f"{path.name} 沒有找到官方 action")
            for name, revision in actions:
                self.assertRegex(
                    revision,
                    r"^[a-f0-9]{40}$",
                    f"{path.name} 的 {name} 未固定到完整 commit",
                )


if __name__ == "__main__":
    unittest.main()
