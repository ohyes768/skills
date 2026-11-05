"""分层覆盖、利润桥和分页合同。空值不得变成零，错误游标不得被当成读完。"""

import json
from copy import deepcopy
from decimal import Decimal

import pytest
import run_pipeline
from analysis_pack import (
    asset_transfer_support,
    build_analysis_pack,
    dupont_driver,
    fact_availability,
    packet_items,
    profit_attribution,
    qualitative_claim_errors,
)
from artifacts import read_json, write_json
from build_report_spec import build_spec
from pack_context import build_packet
from pack_context import main as pack_main
from test_f10_pipeline import archive_fixture, report_spec

ROOT_SKELETON = (
    __import__("pathlib").Path(__file__).resolve().parents[1]
    / "references" / "report-spec-skeleton.json"
)


def _component(metric, delta, status="computed"):
    return {"metric": metric, "status": status, "delta": delta}


def _bridge(deltas):
    return [_component(metric, delta) for metric, delta in deltas.items()]


@pytest.fixture
def f10_run(run_dir, monkeypatch):
    archive = archive_fixture()

    def fetch(code, dates, path, **kwargs):
        write_json(path / "structured_financials.json", archive)
        return {**deepcopy(archive), "reused": False}

    monkeypatch.setattr("fetch_structured.fetch_structured", fetch)
    result, code = run_pipeline.cmd_prepare("002093", "2024-06-30", run_dir)
    assert code == 0, result
    result, code = run_pipeline.cmd_compute(run_dir)
    assert code == 0, result
    return run_dir


def test_missing_bridge_delta_stays_null():
    result = profit_attribution(_bridge({
        "revenue": "10", "cost_of_sales": None, "selling_expenses": "1",
        "admin_expenses": "1", "r_and_d_expense": "1", "finance_costs": "1",
        "investment_income": "1",
    }))
    assert result["supported"] is False
    assert result["driver"] is None
    cost = _component("cost_of_sales", None, status="missing")
    assert cost["delta"] is None


def test_unique_driver_can_be_supported_when_bridge_is_complete():
    result = profit_attribution(_bridge({
        "revenue": "30", "cost_of_sales": "2", "selling_expenses": "1",
        "admin_expenses": "1", "r_and_d_expense": "1", "finance_costs": "1",
        "investment_income": "1",
    }))
    assert result == {
        "supported": True, "driver": "revenue", "missing": [],
        "reason": "单一科目差额严格大于其余已映射桥接项",
    }


def test_balance_direction_does_not_confirm_asset_transfer():
    result = asset_transfer_support(Decimal(10), Decimal(-4))
    assert result["supported"] is False
    assert result["observed"] == "fixed_up_cip_down"


def test_dupont_driver_needs_comparable_factors():
    missing = dupont_driver((Decimal("0.2"), Decimal(1), Decimal(2)), (None, None, None))
    assert missing["supported"] is False
    assert missing["effects"] is None
    found = dupont_driver(
        (Decimal("0.2"), Decimal(1), Decimal(2)),
        (Decimal("0.1"), Decimal(1), Decimal(2)),
    )
    assert found["supported"] is True
    assert found["driver"] == "net_margin"


def test_fact_layers_keep_archive_field_and_mapping_distinct():
    slots = {("2024-06-30", "income"): {"availability": "present"}}
    assert fact_availability(
        {"value": None, "review_status": "missing", "source": "structured",
         "raw_label": "SALE_EXPENSE", "source_ref": {
             "report_date": "2024-06-30", "report_kind": "income", "field": "SALE_EXPENSE"}},
        slots,
    ) == "field_null"
    assert fact_availability(
        {"value": None, "raw_label": "__UNMAPPED__", "source": "structured",
         "source_ref": {"field": "__UNMAPPED__", "report_date": "2024-06-30",
                        "report_kind": "income"}},
        slots,
    ) == "unmapped"
    failed = {("2024-06-30", "income"): {"availability": "fetch_failed"}}
    assert fact_availability(
        {"value": None, "source": "structured", "raw_label": "NETPROFIT",
         "source_ref": {"field": "NETPROFIT", "report_date": "2024-06-30",
                        "report_kind": "income"}},
        failed,
    ) == "fetch_failed"
    empty = {("2024-06-30", "income"): {"availability": "no_data"}}
    assert fact_availability(
        {"value": None, "source": "structured", "raw_label": "NETPROFIT",
         "source_ref": {"field": "NETPROFIT", "report_date": "2024-06-30",
                        "report_kind": "income"}},
        empty,
    ) == "no_data"


def test_f10_sample_keeps_comparison_balance_sheet(f10_run):
    pack = build_analysis_pack(f10_run)
    assert pack["counts"]["archive_present"] == 9
    opening = next(
        row for row in pack["records"]
        if row.get("role") == "opening" and row["report_kind"] == "balance")
    assert opening["availability"] == "present"
    limit = next(row for row in pack["narrative_limits"]
                 if row["code"] == "comparison_balance_sheet")
    assert "不得写成比较期资产负债表未取得" in limit["text"]
    assert "goodwill" in next(
        row["metrics"] for row in pack["records"] if row["layer"] == "model_input")
    selling = next(
        row for row in pack["records"]
        if row.get("metric") == "selling_expenses" and row["layer"] == "field")
    assert selling["availability"] == "field_null"
    bridge = {row["metric"]: row for row in pack["profit_bridge"]["components"]}
    assert bridge["investment_income"]["status"] == "unmapped"
    assert bridge["investment_income"]["delta"] is None
    assert pack["qualitative_support"]["profit_primary_attribution"]["supported"] is False
    assert pack["qualitative_support"]["asset_transfer"]["supported"] is False
    assert pack["qualitative_support"]["dupont_yoy_driver"]["supported"] is False


def test_failure_reasons_stay_distinct_from_a_present_statement(f10_run):
    archive = read_json(f10_run / "structured_financials.json")
    archive["reports"]["2023-06-30"].pop("income")
    archive["reports"]["2023-06-30"].pop("cashflow")
    archive["fetch_failures"] = {
        "2023-06-30/income": {"reason": "no_data", "detail": "empty"},
        "2023-06-30/cashflow": {"reason": "fetch_failed", "detail": "HTTP 500"},
    }
    write_json(f10_run / "structured_financials.json", archive)
    result, code = run_pipeline.cmd_compute(f10_run)
    assert code == 2, result
    pack = read_json(f10_run / "analysis_pack.json")
    slots = {(row["report_date"], row["report_kind"]): row["availability"]
             for row in pack["records"] if row["layer"] == "archive"}
    assert slots[("2023-06-30", "income")] == "no_data"
    assert slots[("2023-06-30", "cashflow")] == "fetch_failed"
    assert slots[("2023-12-31", "balance")] == "present"
    assert any(row["availability"] == "not_calculated" and row["layer"] == "calculation"
               for row in pack["records"])


def test_compute_and_pack_context_share_cursor_path(f10_run):
    result, code = run_pipeline.cmd_compute(f10_run)
    assert code == 0, result
    assert result["continuation"]["cursor_field"] == "packet.next_cursor"
    assert result["packet"] == result["context"]["packet"]
    cursor = result["packet"]["next_cursor"]
    assert cursor
    seen = []
    steps = 0
    while cursor:
        page = build_packet(f10_run, "analyze", f"page-{steps}", cursor=cursor, max_chars=1500)
        seen.extend(page["packet"]["items"])
        cursor = page["packet"]["next_cursor"]
        steps += 1
        assert steps < 40
    assert result["packet"]["items"] + seen == packet_items(f10_run)
    with pytest.raises(ValueError, match="stale|invalid"):
        build_packet(f10_run, "analyze", "bad", cursor="not-a-cursor")


def test_invalid_cursor_is_not_an_end_marker(f10_run, capsys):
    code = pack_main(["--run-dir", str(f10_run), "--request-id", "bad", "--cursor", "nope"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed"
    assert payload["ended"] is False
    assert "next_cursor" not in payload


def test_unsupported_claims_are_blocked_and_supported_driver_is_not(f10_run):
    pack = build_analysis_pack(f10_run)
    blocked = qualitative_claim_errors(pack, [
        "比较期资产负债表未取得。",
        "利润增速更快主要来自投资收益。",
        "固定资产增加可以确认转固。",
        "杜邦分析已经确定 ROE 同比改善的主要驱动。",
    ])
    assert len(blocked) == 4
    allowed = qualitative_claim_errors(pack, ["收入与成本的变动方向需要分开看。"])
    assert allowed == []
    supported = {
        "narrative_limits": [{"code": "comparison_balance_sheet", "availability": "present"}],
        "qualitative_support": {
            "profit_primary_attribution": {"supported": True, "driver": "revenue"},
            "asset_transfer": {"supported": False},
            "dupont_yoy_driver": {"supported": True, "driver": "net_margin"},
        },
    }
    assert qualitative_claim_errors(supported, ["利润变化主要来自收入增长。"]) == []
    assert qualitative_claim_errors(supported, ["利润主要来自投资收益。"])


def test_core_todo_states_remaining_sentences(f10_run):
    skeleton = json.loads(ROOT_SKELETON.read_text(encoding="utf-8"))
    spec, _notes = build_spec(f10_run, skeleton)
    core = next(section for section in spec["sections"] if section["anchor"] == "## 核心结论")
    assert len(core["statements"]) == 4
    todo = next(item for item in spec["_paragraphs_todo"] if item["anchor"] == "## 核心结论")
    assert todo["position"] == 1
    assert todo["editable"] is True
    assert todo["digits"] == "forbidden"
    assert todo["sentence_budget"]["core_statement_sentences"] == 4
    assert todo["sentence_budget"]["qualitative_sentences_max"] == 1
    assert any("资产负债表" in text for text in todo["missing_limits"])


def test_delivered_false_claim_fails_validation(f10_run):
    spec = report_spec(f10_run)
    spec["sections"][2]["paragraphs"] = ["比较期资产负债表未取得。"]
    path = f10_run / "report_spec.json"
    write_json(path, spec)
    result, code = run_pipeline.cmd_report(f10_run, spec_path=path, independent_review=True)
    assert code != 0
    assert any("comparison balance sheet" in issue for issue in result["issues"])
