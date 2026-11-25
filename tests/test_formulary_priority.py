from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.pipeline.formulary_priority import optional_priority, prioritize
from tools.pipeline.fetch_structured import fetch_batch
from tools.pipeline.static_release import active_catalog
from tools.sources import official


FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = FIXTURES / "pipeline_sources"
A = "衛署藥製字第016162號"
B = "衛部藥製字第123456號"
PRIVATE = "Privatehospitalingredient"


class FormularyPriorityTests(unittest.TestCase):
    def active(self):
        return active_catalog(official.build_bundle("licenses", (SOURCES / "licenses.raw").read_bytes(), allow_small=True))

    def test_stable_tiers_exact_atc_and_same_row_english_tokens(self):
        active = self.active()
        active.update({"C": {"license_code": "", "drug_name_en": "Other"}, "D": {"license_code": "", "drug_name_en": "Other"}})
        csv = "藥名,ATC碼,狀態\nNew,A01AA02,使用中\nUnrelated,A01AA01,使用中\nOther,A01AA03,停用\n"
        pending = ["C", A, "D", B]
        ordered, counts = prioritize(pending, active, SOURCES, csv.encode())
        self.assertEqual(ordered, [B, A, "C", "D"])
        self.assertEqual(counts, {"tier1": 1, "tier2": 1, "tier3": 2})

        # A matching word under a different ATC must not promote A into tier 1.
        _, counts = prioritize([A], active, SOURCES, "藥名,ATC碼,狀態\nTEST,A01AA02,使用中\nOTHER,A01AA01,使用中\n".encode())
        self.assertEqual(counts["tier2"], 1)

    def test_disabled_partial_atc_substrings_and_generic_names_do_not_promote(self):
        payload = "\ufeff藥名,ATC碼,狀態\nTEST,A01AA01,停用\nNEW,A01AA0,使用中\nTablet,A01AA02,使用中\n"
        ordered, counts = prioritize([A, B], self.active(), SOURCES, payload.encode())
        self.assertEqual(ordered, [B, A])
        self.assertEqual(counts, {"tier1": 0, "tier2": 1, "tier3": 1})

    def test_official_ingredient_token_can_supply_name_match(self):
        payload = "藥名,ATC碼,狀態\nIngredient,A01AA01,使用中\n"
        _, counts = prioritize([A], self.active(), SOURCES, payload.encode())
        self.assertEqual(counts["tier1"], 1)

    def test_secret_unset_download_error_or_invalid_csv_falls_back_without_leaks(self):
        for secret, download in [
            ("", lambda _: self.fail("unset secret must not download")),
            ("https://private.invalid/secret", lambda _: (_ for _ in ()).throw(ValueError(PRIVATE))),
            ("https://private.invalid/secret", lambda _: f"private,{PRIVATE}".encode()),
        ]:
            with self.subTest(secret=bool(secret)), patch.dict(os.environ, {"FORMULARY_CSV_URL": secret}), redirect_stdout(io.StringIO()) as log:
                ordered = optional_priority([A, B], self.active(), SOURCES, download=download)
            self.assertEqual(ordered, [A, B])
            self.assertIn("Warning:", log.getvalue())
            self.assertNotIn(PRIVATE, log.getvalue())
            self.assertNotIn("private.invalid", log.getvalue())

    def test_priority_affects_pending_only_and_never_persists_formulary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "official"
            shutil.copytree(SOURCES, source)
            # Use a private token only in the in-memory hospital CSV and official
            # name passed to prioritization. It must not enter structured state.
            payload = f"藥名,ATC碼,狀態\nNew {PRIVATE},A01AA02,使用中\n".encode()
            calls = []
            real_priority = optional_priority
            def priority(pending, active, source_dir):
                return real_priority(pending, active, source_dir, download=lambda _: payload)
            def fetch(query):
                calls.append(query.license_code)
                return (FIXTURES / f"structured-{query.license_code}.xml").read_bytes()
            output = root / "structured"
            with patch.dict(os.environ, {"FORMULARY_CSV_URL": "https://private.invalid/secret"}), patch("tools.pipeline.fetch_structured.optional_priority", side_effect=priority), redirect_stdout(io.StringIO()) as log:
                first = fetch_batch(source / "licenses.raw", output, max_items=1, request_delay=0, fetch=fetch)
                second = fetch_batch(source / "licenses.raw", output, max_items=1, request_delay=0, fetch=fetch)
            self.assertEqual(calls, ["51123456", "01016162"])
            self.assertFalse(first["complete"])
            self.assertTrue(second["complete"])
            self.assertIn("priority tier1: 1", log.getvalue())
            for value in [log.getvalue(), json.dumps(first), json.dumps(second), *(path.read_text() for path in output.rglob("*.json"))]:
                self.assertNotIn(PRIVATE, value)
                self.assertNotIn("private.invalid", value)
