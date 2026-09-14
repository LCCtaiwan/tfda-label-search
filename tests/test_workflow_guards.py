from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
