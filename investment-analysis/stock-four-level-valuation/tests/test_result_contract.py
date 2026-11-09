"""Contract and real subprocess CLI tests with explicitly fictional fixtures."""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SCRIPTS))
if importlib.util.find_spec("validate_result"):
    from validate_result import check, dumps, finalize, load_json, save_atomic
else:
    def missing(*args, **kwargs):
        raise AssertionError("validate_result not implemented")
    check = dumps = finalize = load_json = save_atomic = missing

LEVELS = ("heavy_position", "add_position", "reduce_position", "full_exit")
OUTPUT_KEYS = {"schema_version", "skill_version", "code", "name", "currency", "as_of", "status", "levels", "valuation", "evidence", "data_gaps", "confidence", "risks", "invalidation_conditions", "summary", "analysis", "report_md"}


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.skill = self.tmp / "SKILL.md"
        self.skill.write_text("---\nname: fictional-test\nmetadata:\n  version: '1.0.0'\n---\n虚构测试\n", encoding="utf-8")
        self.draft = fixture("ready.json")
        self.stock = fixture("stock.json")

    def finish(self, draft=None):
        return finalize(self.draft if draft is None else draft, self.stock, skill_path=self.skill)

    def test_ready_schema_and_independent_values(self):
        result = self.finish()
        self.assertEqual(set(result), OUTPUT_KEYS)
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["schema_version"], "1.0.0")
        self.assertEqual(result["skill_version"], "1.0.0")
        self.assertEqual(result["levels"]["heavy_position"], {"price": Decimal(16), "pe": Decimal(10), "pb": Decimal(4)})
        self.assertEqual([result["levels"][x]["price"] for x in LEVELS], [16, 20, 28, 36])
        valuation = result["valuation"]
        self.assertEqual(valuation["calculated"]["heavy_position"]["exact_price"], "16")
        self.assertEqual(valuation["scenario_values"]["bear"]["price"], 12)
        self.assertEqual(valuation["sensitivity_values"][0]["delta_pct"], -25)
        self.assertEqual(valuation["level_metrics"]["heavy_position"]["dividend_yield_pct"], 5)
        self.assertEqual(valuation["decisions"]["heavy_position"]["model"]["margin"], "0")

    def test_pb_ready_and_common_equity_anchor(self):
        val = self.draft["valuation"]
        val["primary_method"] = "pb_multiple"
        for entry in list(val["decisions"].values()) + list(val["scenarios"].values()) + val["sensitivity"]:
            model = entry["model"]
            entry["model"] = {"method": "pb_multiple", "bvps": model["eps"], "multiple": model["multiple"]}
        self.assertEqual(self.finish()["levels"]["heavy_position"]["price"], 16)
        val["decisions"]["full_exit"]["model"]["bvps"] = "3"
        with self.assertRaises(ValueError):
            self.finish()

    def test_cashflow_ready_reports_present_not_terminal_price(self):
        val = self.draft["valuation"]
        val["primary_method"] = "equity_cashflow_pv"
        def model(amount):
            return {"method": "equity_cashflow_pv", "cashflows": [amount], "discount_rate": "0.1", "cashflow_basis": "dividend", "finite_life": True, "terminal": {"kind": "value", "value": "0"}}
        for key, amount in zip(LEVELS, ("11", "22", "33", "44")):
            val["decisions"][key]["model"] = model(amount)
        for key, amount in zip(("bear", "base", "bull"), ("11", "22", "33")):
            val["scenarios"][key]["model"] = model(amount)
        val["sensitivity"][0]["model"] = model("5.5")
        val["sensitivity"][1]["model"] = model("11")
        self.assertEqual([self.finish()["levels"][key]["price"] for key in LEVELS], [10, 20, 30, 40])

    def test_inputs_are_not_mutated(self):
        draft, stock = copy.deepcopy(self.draft), copy.deepcopy(self.stock)
        self.finish()
        self.assertEqual(self.draft, draft)
        self.assertEqual(self.stock, stock)

    def test_report_has_derived_rows_analysis_evidence_and_risks(self):
        result = self.finish()
        report = result["report_md"]
        for value in ["16.00", "20.00", "28.00", "36.00", "12.00", "40.00", "5.0000", "2026-11-08", "ready", "fixture", self.draft["analysis"]["risk"], self.draft["risks"][0]]:
            self.assertIn(value, report)
        self.assertIn("TTM", report)
        self.assertIn("不证明", report)

    def test_all_nonready_states_all_null_and_replayable(self):
        for status in ("insufficient_data", "blocked", "not_applicable"):
            with self.subTest(status=status):
                draft = fixture("insufficient.json")
                draft["status"] = status
                result = self.finish(draft)
                self.assertIsNone(result["valuation"])
                self.assertEqual(result["analysis"], draft["analysis"])
                self.assertEqual(result["levels"], {key: {"price": None, "pe": None, "pb": None} for key in LEVELS})
                self.assertEqual(check(result, self.stock, skill_path=self.skill)["status"], "ok")
                self.assertNotIn("None", result["report_md"])
        draft = fixture("insufficient.json")
        draft["evidence"] = [{"kind": "input", "origin": "inline:2026-11-08:调用方摘要", "id": "I1",
                              "title": "内联线索", "locator": "正文", "period": "未知",
                              "published_at": None, "accessed_at": None, "verification": "unverified"}]
        report = self.finish(draft)["report_md"]
        self.assertNotIn("None", report)
        self.assertIn("未记录", report)

    def test_nonready_requires_explanation_and_null_valuation(self):
        draft = fixture("insufficient.json")
        draft["data_gaps"] = []
        with self.assertRaises(ValueError):
            self.finish(draft)
        draft = fixture("insufficient.json")
        draft["valuation"] = self.draft["valuation"]
        with self.assertRaises(ValueError):
            self.finish(draft)

    def test_strict_identity_date_currency_and_stock_shape(self):
        for field, value in [("code", 1), ("code", "00001"), ("code", "０００００１"), ("name", "另一公司"), ("as_of", "2026-11-07"), ("as_of", "2026-02-30"), ("as_of", "20261108"), ("currency", "USD")]:
            draft = copy.deepcopy(self.draft)
            draft[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.finish(draft)
        self.stock["unknown"] = "x"
        with self.assertRaises(ValueError):
            self.finish()

    def test_missing_or_unknown_fields_at_each_contract_layer(self):
        for path in [(), ("confidence",), ("analysis",), ("valuation",), ("valuation", "metric_inputs"), ("valuation", "decisions", "heavy_position")]:
            for operation in ("add", "delete"):
                draft = copy.deepcopy(self.draft)
                node = draft
                for key in path:
                    node = node[key]
                if operation == "add":
                    node["unknown"] = 1
                else:
                    del node[next(iter(node))]
                with self.subTest(path=path, operation=operation), self.assertRaises(ValueError):
                    self.finish(draft)

    def test_draft_cannot_supply_computed_output_or_versions(self):
        for key in ("levels", "report_md", "skill_version", "schema_version"):
            draft = copy.deepcopy(self.draft)
            draft[key] = {}
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.finish(draft)
        self.draft["valuation"]["calculated"] = {}
        with self.assertRaises(ValueError):
            self.finish()

    def test_bad_text_status_confidence_and_list_fields(self):
        for field, value in [("status", "unknown"), ("summary", " "), ("confidence", {"level": "sure", "reason": "原因"}), ("confidence", {"level": "low", "reason": ""}), ("risks", [False]), ("invalidation_conditions", "风险"), ("data_gaps", [""])]:
            draft = copy.deepcopy(self.draft)
            draft[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.finish(draft)
        self.draft["analysis"]["business"] = "English-only text"
        with self.assertRaises(ValueError):
            self.finish()

    def test_evidence_required_and_reference_must_be_usable(self):
        for mutation in ("empty", "unverified", "unknown_id", "duplicate_id", "empty_refs"):
            draft = copy.deepcopy(self.draft)
            if mutation == "empty":
                draft["evidence"] = []
            elif mutation == "unverified":
                draft["evidence"][0]["verification"] = "unverified"
            elif mutation == "unknown_id":
                draft["valuation"]["scenarios"]["bear"]["evidence_ids"] = ["missing"]
            elif mutation == "duplicate_id":
                draft["evidence"].append(copy.deepcopy(draft["evidence"][0]))
            else:
                draft["valuation"]["decisions"]["full_exit"]["evidence_ids"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.finish(draft)

    def test_source_metadata_rejects_bad_dates_protocols_and_shape(self):
        for field, value in [("published_at", "2026-11-09"), ("accessed_at", "2026-2-3"), ("origin", "javascript:alert(1)"), ("origin", "file:///etc/passwd"), ("origin", "https://"), ("origin", ""), ("kind", "magic"), ("verification", "verified"), ("locator", ""), ("period", "")]:
            draft = copy.deepcopy(self.draft)
            draft["evidence"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.finish(draft)
        self.draft["evidence"][0]["extra"] = "x"
        with self.assertRaises(ValueError):
            self.finish()

    def test_source_read_or_reused_is_status_not_filesystem_or_network_access(self):
        for origin in ("https://example.invalid/no-fetch", "F:/fictional/does-not-exist.json", "./missing-local.json", "f:/fictional/lowercase-drive.json", "//unc-host/share/report.json", "\\\\unc-host\\share\\report.json", "inline:2026-11-08:调用方内联年报摘要"):
            draft = copy.deepcopy(self.draft)
            draft["evidence"][0].update(origin=origin, verification="reused", accessed_at=None)
            self.assertEqual(self.finish(draft)["status"], "ready")

    def test_four_decisions_must_be_same_model_and_common_anchor(self):
        for model in [{"method": "pe_multiple", "eps": "3", "multiple": "18"}, {"method": "pb_multiple", "bvps": "4", "multiple": "9"}]:
            draft = copy.deepcopy(self.draft)
            draft["valuation"]["decisions"]["full_exit"]["model"] = model
            with self.subTest(model=model), self.assertRaises(ValueError):
                self.finish(draft)

    def test_reject_out_of_order_and_rounding_collision_without_sort(self):
        for multiple in ("7", "10", "10.001"):
            self.draft["valuation"]["decisions"]["reduce_position"]["model"]["multiple"] = multiple
            with self.subTest(multiple=multiple), self.assertRaises(ValueError):
                self.finish()

    def test_scenario_order_and_exact_three_keys(self):
        self.draft["valuation"]["scenarios"]["bear"]["model"]["multiple"] = "100"
        with self.assertRaises(ValueError):
            self.finish()
        self.draft = fixture("ready.json")
        self.draft["valuation"]["scenarios"]["fourth"] = self.draft["valuation"]["scenarios"]["bear"]
        with self.assertRaises(ValueError):
            self.finish()

    def test_metric_null_missingness_and_basis(self):
        metrics = self.draft["valuation"]["metric_inputs"]
        metrics.update(ttm_eps=None, common_bvps="-1", annual_dps="0")
        result = self.finish()
        self.assertEqual(result["levels"]["heavy_position"], {"price": 16, "pe": None, "pb": None})
        self.assertEqual(result["valuation"]["level_metrics"]["heavy_position"]["dividend_yield_pct"], 0)
        metrics["dps_basis"] = "none"
        with self.assertRaises(ValueError):
            self.finish()

    def test_present_metric_values_require_usable_evidence(self):
        self.draft["valuation"]["metric_inputs"]["evidence_ids"] = []
        with self.assertRaises(ValueError):
            self.finish()

    def test_sensitivity_count_reference_and_changed_parameter(self):
        original = copy.deepcopy(self.draft["valuation"]["sensitivity"])
        for value in [[], original[:1], original * 5]:
            self.draft["valuation"]["sensitivity"] = value
            with self.subTest(count=len(value)), self.assertRaises(ValueError):
                self.finish()
        self.draft["valuation"]["sensitivity"] = original
        original[0]["model"] = {"method": "pe_multiple", "eps": "2.00", "multiple": 8, "margin": 0}
        with self.assertRaises(ValueError):
            self.finish()
        original[0]["base_level"] = "missing"
        with self.assertRaises(ValueError):
            self.finish()

    def test_sensitivity_must_keep_same_model(self):
        self.draft["valuation"]["sensitivity"][0]["model"] = {"method": "pb_multiple", "bvps": "3", "multiple": "4"}
        with self.assertRaises(ValueError):
            self.finish()

    def test_check_round_trip(self):
        result = self.finish()
        path = self.tmp / "result.json"
        path.write_text(dumps(result), encoding="utf-8")
        self.assertEqual(check(load_json(path), self.stock, skill_path=self.skill), {"status": "ok", "code": "000001", "as_of": "2026-11-08"})

    def test_check_rejects_all_derived_mutations(self):
        result = self.finish()
        mutations = [(("levels", "heavy_position", "price"), Decimal("16.01")), (("levels", "heavy_position", "pe"), True), (("levels", "heavy_position", "pb"), "4"), (("valuation", "calculated", "heavy_position", "exact_price"), "17"), (("valuation", "scenario_values", "bear", "price"), 13), (("valuation", "sensitivity_values", 0, "delta_pct"), -20), (("valuation", "level_metrics", "heavy_position", "dividend_yield_pct"), 10), (("report_md",), "伪造报告"), (("skill_version",), "0.9.0"), (("schema_version",), "2.0.0")]
        for path, value in mutations:
            bad = copy.deepcopy(result)
            node = bad
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                check(bad, self.stock, skill_path=self.skill)

    def test_check_rejects_unknown_nested_derived_keys(self):
        result = self.finish()
        result["levels"]["heavy_position"]["extra"] = 0
        with self.assertRaises(ValueError):
            check(result, self.stock, skill_path=self.skill)

    def test_check_rejects_report_drift_after_audit_or_analysis_changes(self):
        for path in [("analysis", "risk"), ("valuation", "decisions", "heavy_position", "rationale")]:
            result = self.finish()
            node = result
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = "已经改变的假设与分析。"
            with self.subTest(path=path), self.assertRaises(ValueError):
                check(result, self.stock, skill_path=self.skill)

    def test_decimal_json_emission_preserves_cents_beyond_float_precision(self):
        encoded = dumps({"price": Decimal("12345678901234567890.01")})
        self.assertIn("12345678901234567890.01", encoded)
        self.assertEqual(json.loads(encoded, parse_float=Decimal)["price"], Decimal("12345678901234567890.01"))
        with self.assertRaises(ValueError):
            dumps({"price": Decimal("NaN")})

    def test_duplicate_keys_nan_infinity_and_malformed_json_rejected(self):
        for text in ['{"a":1,"a":2}', '{"x":{"a":1,"a":2}}', '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e999999}', '{bad']:
            path = self.tmp / "bad.json"
            path.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                load_json(path)

    def test_version_requires_metadata_frontmatter_and_is_not_hardcoded(self):
        self.skill.write_text("---\nmetadata:\n  version: 1.2.3\n---\n", encoding="utf-8")
        self.assertEqual(self.finish()["skill_version"], "1.2.3")
        for text in ["metadata:\n  version: 1.0.0", "---\nversion: 1.0.0\n---\n", "---\nmetadata:\n  version: invalid\n---\n"]:
            self.skill.write_text(text, encoding="utf-8")
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.finish()

    def test_atomic_save_failure_preserves_old_output_and_cleans_temp(self):
        path = self.tmp / "result.json"
        path.write_text("OLD", encoding="utf-8")
        self.assertTrue(importlib.util.find_spec("validate_result"), "validate_result not implemented")
        with patch("validate_result.os.replace", side_effect=OSError("simulated disk replacement failure")), \
                self.assertRaises(OSError):
            save_atomic(path, '{"new":true}')
        self.assertEqual(path.read_text(encoding="utf-8"), "OLD")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["SKILL.md", "result.json"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        for path in SCRIPTS.glob("*.py"):
            shutil.copy2(path, scripts / path.name)
        self.cli = scripts / "validate_result.py"
        (self.tmp / "SKILL.md").write_text("---\nmetadata:\n  version: 1.0.0\n---\n", encoding="utf-8")
        self.input = self.tmp / "draft.json"
        self.stock = self.tmp / "stock.json"
        self.output = self.tmp / "result.json"
        shutil.copy2(FIXTURES / "ready.json", self.input)
        shutil.copy2(FIXTURES / "stock.json", self.stock)

    def run_cli(self, *args):
        self.assertTrue(self.cli.exists(), "validate_result CLI not implemented")
        return subprocess.run([sys.executable, "-X", "utf8", "-S", str(self.cli), *map(str, args)], capture_output=True, encoding="utf-8", timeout=15, check=False)

    def finish_cli(self, output=None):
        return self.run_cli("finalize", "--input", self.input, "--stock", self.stock, "--output", output or self.output)

    def test_cli_finalize_check_stdout_file_identical_and_inputs_unchanged(self):
        before = (self.input.read_bytes(), self.stock.read_bytes())
        proc = self.finish_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(proc.stdout, self.output.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(proc.stdout)["levels"]["heavy_position"]["price"], 16)
        checked = self.run_cli("check", "--input", self.output, "--stock", self.stock)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["status"], "ok")
        self.assertEqual((self.input.read_bytes(), self.stock.read_bytes()), before)

    def test_cli_error_empty_stdout_preserves_existing_output(self):
        self.output.write_text("OLD", encoding="utf-8")
        self.input.write_text('{"code":"000001","code":"000002"}', encoding="utf-8")
        proc = self.finish_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertIn("duplicate", proc.stderr)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "OLD")

    def test_cli_check_tampered_file_fails_without_stdout(self):
        proc = self.finish_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(self.output.read_text(encoding="utf-8"))
        result["levels"]["heavy_position"]["price"] = 17
        self.output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        proc = self.run_cli("check", "--input", self.output, "--stock", self.stock)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertTrue(proc.stderr)

    def test_cli_rejects_aliases_of_input_and_stock(self):
        for output in (self.input, self.stock):
            before = output.read_bytes()
            proc = self.finish_cli(output)
            with self.subTest(output=output.name):
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertEqual(output.read_bytes(), before)

    def test_cli_rejects_hardlink_alias(self):
        alias = self.tmp / "alias.json"
        os.link(self.input, alias)
        before = self.input.read_bytes()
        proc = self.finish_cli(alias)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(self.input.read_bytes(), before)

    def test_cli_missing_input_and_directory_output_errors(self):
        proc = self.finish_cli(self.tmp)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")
        self.input.unlink()
        proc = self.finish_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")

    def test_cli_help_and_missing_argument(self):
        proc = self.run_cli("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("finalize", proc.stdout)
        self.assertIn("check", proc.stdout)
        proc = self.run_cli("finalize", "--input", self.input)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main()
