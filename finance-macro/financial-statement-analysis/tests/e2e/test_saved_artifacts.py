"""真实样本保存产物回归：产物缺失时 skip（离线测试不依赖运行产物）。"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

RUN_DIR = Path(__file__).parents[3] / "output" / "financial-statement-analysis" / "600519-2024"

pytestmark = pytest.mark.skipif(not RUN_DIR.exists(), reason="acceptance run artifacts not present")


def read(name: str):
    return json.loads((RUN_DIR / name).read_text(encoding="utf-8"))


def test_document_identification():
    doc = read("document.json")
    assert doc["company_name"] == "贵州茅台酒股份有限公司"
    assert doc["stock_code"] == "600519"
    assert doc["report_type"] == "annual"
    assert doc["audit_status"] == "audited"
    assert doc["applicability"]["framework"] == "general"


def test_key_facts_match_manual_annotation():
    facts = {f["fact_id"]: f for f in read("financials.json")["facts"]}

    annotated = {
        "f-0003": "170899152276.34",
        "f-0005": "89334728025.90",
        "f-0007": "86228146421.62",
        "f-0009": "298944579918.70",
        "f-0011": "242011315120.60",
        "f-0013": "233105984399.47",
        "f-0019": "169970089257.83",
        "f-0021": "92463692168.43",
    }
    for fact_id, expected in annotated.items():
        assert Decimal(facts[fact_id]["value"]) == Decimal(expected), fact_id
        assert facts[fact_id]["scope"] == "consolidated"
        assert facts[fact_id]["evidence_ids"], fact_id


def test_metrics_and_reconciliation():
    metrics = {m["metric_id"]: m for m in read("metrics.json")["metrics"]}
    assert Decimal(metrics["revenue_yoy"]["value"]).quantize(Decimal("0.0001")) == Decimal("0.1571")
    assert Decimal(metrics["roe_group_simple"]["value"]).quantize(Decimal("0.0001")) == Decimal("0.3837")
    assert Decimal(metrics["cfo_to_net_profit_group"]["value"]).quantize(Decimal("0.001")) == Decimal("1.035")
    assert metrics["inventory_turnover"]["status"] == "computed"

    check = {c["check_id"]: c for c in read("validation.json")["checks"]}["cash_reconciliation"]
    assert check["status"] == "passed"
    assert Decimal(check["residual"]) == Decimal("0.00")


def test_report_validation_passed():
    assert read("report_validation.json")["passed"] is True


def test_context_saving_target():
    pages = [
        json.loads(line)
        for line in (RUN_DIR / "pages.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    full_chars = sum(len(b["text"]) for p in pages for b in p["blocks"])
    usage = [
        json.loads(line)
        for line in (RUN_DIR / "context_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    delivered = sum(u["character_count"] for u in usage)
    assert delivered <= full_chars * 0.5, f"delivered {delivered} vs full {full_chars}"
