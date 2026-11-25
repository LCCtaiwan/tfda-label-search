from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorkflowGuardTests(unittest.TestCase):
    def test_schedule_limits_and_authorization_truth_table(self):
        workflow = (ROOT / ".github/workflows/refresh-data.yml").read_text()
        self.assertIn('cron: "23 2 * * *"', workflow)
        for choice in ("5", "25", "50", "100", "500"):
            self.assertIn(f'          - "{choice}"', workflow)
        self.assertIn('--request-delay 2', workflow)
        guard = re.search(r"if: (vars.TFDA_API_CALLS_AUTHORIZED[^\n]+)", workflow)[1]
        incremental = re.search(r"INCREMENTAL_AUTHORIZATION: \$\{\{ (.+) \}\}", workflow)[1]
        max_items = re.search(r"MAX_ITEMS: \$\{\{ (.+) \}\}", workflow)[1]
        max_windows = re.search(r"MAX_UPDATE_WINDOWS: \$\{\{ (.+) \}\}", workflow)[1]

        def evaluate(expression, values):
            for key, value in values.items():
                expression = expression.replace(key, repr(value))
            expression = expression.replace('&&', ' and ').replace('||', ' or ').replace('== true', '== True').replace('!= true', '!= True')
            return eval(expression, {"__builtins__": {}}, {})

        for scheduled in (False, True):
            for api in (False, True):
                for authorized in (False, True):
                    for ack in (False, True):
                        for incremental_ack in (False, True):
                            values = {
                                'github.event_name': 'schedule' if scheduled else 'workflow_dispatch',
                                'vars.TFDA_API_CALLS_AUTHORIZED': str(api).lower(),
                                'vars.TFDA_SCHEDULE_AUTHORIZED': str(authorized).lower(),
                                'inputs.authorization_ack': ack,
                                'inputs.incremental_authorization_ack': incremental_ack,
                                'inputs.max_items': '5', 'inputs.max_update_windows': '3',
                            }
                            self.assertEqual(evaluate(guard, values), not (api and (authorized if scheduled else ack)))
                            self.assertEqual(evaluate(incremental, values), 'authorized' if (authorized if scheduled else incremental_ack) else 'not_authorized')
                            self.assertEqual(evaluate(max_items, values), '500' if scheduled else '5')
                            self.assertEqual(evaluate(max_windows, values), '1' if scheduled else '3')

    def test_automatic_deployment_is_pinned_and_only_reviewed_smoke_records_approval(self):
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text()
        self.assertIn('workflows: ["Refresh TFDA data state"]', workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.event == 'schedule'", workflow)
        self.assertIn("--name scheduled-refresh-revisions", workflow)
        self.assertIn("needs.build.outputs.auto_deploy == 'true' && 'github-pages-auto' || 'github-pages'", workflow)
        record = workflow.split('  record-approved-app:', 1)[1]
        self.assertIn("if: needs.build.outputs.auto_deploy == 'false'", record)
        self.assertIn('needs: [build, deploy, smoke-test]', record)
        self.assertIn('group: tfda-data-state', record)
        self.assertIn('git add approved-app.json', record)
        self.assertNotIn('--min-structured-coverage 0.98', workflow)

    def test_api_authorization_guard_runs_before_official_download(self):
        workflow = (ROOT / ".github" / "workflows" / "refresh-data.yml").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            workflow.index("TFDA_API_CALLS_AUTHORIZED"),
            workflow.index("official_snapshot.py"),
        )
        self.assertIn("inputs.authorization_ack != true", workflow)
        self.assertIn("incremental_authorization_ack:", workflow)
        self.assertIn("回傳可能超過 25 份", workflow)
        self.assertIn(
            '--incremental-authorization "$INCREMENTAL_AUTHORIZATION"',
            workflow,
        )
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
        self.assertIn("--max-age-days 14", workflow)
        self.assertLess(
            workflow.index("--max-age-days 14"),
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
            "steps.data_branch.outputs.initialized != 'true' && steps.source_mode.outputs.mode != 'refresh_all_nine'",
            workflow,
        )
        self.assertGreaterEqual(
            workflow.count("if: steps.source_mode.outputs.mode == 'refresh_all_nine'"),
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
        self.assertLess(
            workflow.index("approval_summary.py"),
            workflow.index("actions/upload-pages-artifact"),
        )
        self.assertIn("approval-summary.md", workflow)
        self.assertIn("$GITHUB_STEP_SUMMARY", workflow)
        self.assertIn("ref: ${{ steps.refs.outputs.app_ref }}", workflow)
        self.assertIn("ref: ${{ steps.refs.outputs.data_ref }}", workflow)
        self.assertIn("--app-revision \"$APP_SHA\"", workflow)
        self.assertIn("--data-revision \"$DATA_SHA\"", workflow)
        self.assertIn("--source-manifest state/official/current/manifest.json", workflow)
        self.assertIn("--require-incremental", workflow)
        self.assertIn("--allow-initial-building", workflow)
        self.assertIn("--max-incremental-lag-days 14", workflow)
        self.assertEqual(workflow.count("--max-official-snapshot-age-days 14"), 2)
        self.assertIn(
            "${{ steps.release.outputs.site_path }}/data/synonyms.json",
            workflow,
        )
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
