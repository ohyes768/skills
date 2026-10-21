"""离线端到端：紧凑输入 → 构造 → 计算 → 同源渲染 → 校验 → verified。"""

import json
from pathlib import Path

import run_pipeline
from test_build_financials import fact_input, prepare_build_run, write_json_file
from test_render_report import revenue_inputs


def run(command: str, run_dir: Path, **kwargs) -> tuple[dict, int]:
    if command == "compute":
        return run_pipeline.cmd_compute(run_dir, pdf_only=True)
    if command == "report":
        return run_pipeline.cmd_report(run_dir)
    return run_pipeline.cmd_review(run_dir)


def test_full_pipeline_to_verified(run_dir):
    """空目录 → 事实构造 → 指标 → 渲染 → 固定校验 → review=verified。"""
    prepare_build_run(run_dir)
    # compute 需要 report 阶段的台账视图（document/company 等），补齐一致元数据
    document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
    document["company_name"] = "测试公司"
    document["stock_code"] = "300000"
    write_json_file(run_dir / "document.json", document)

    fact_inputs_file = {"schema_version": 1, "facts": [
        fact_input(),
        fact_input(metric="net_profit_group", raw_label="净利润",
                   raw_value="123,456,789.00",
                   evidence={"evidence_id": "ev-0001", "locator": {"row": 4, "col": 1}}),
    ]}
    write_json_file(run_dir / "fact_inputs.json", fact_inputs_file)
    result, code = run("compute", run_dir)
    assert (run_dir / "financials.json").exists()
    assert (run_dir / "metrics.json").exists()
    assert result["metric_counts"]["computed"] >= 1

    # revenue_yoy 需要 prior 期间事实；补一条上年同期后重交（消耗一次修复）
    fact_inputs_file["facts"].append(
        fact_input(raw_label="营业收入", raw_value="987,654,321.00", period_ref="prior",
                   evidence={"evidence_id": "ev-0001", "locator": {"row": 0, "col": 2}}))
    write_json_file(run_dir / "fact_inputs.json", fact_inputs_file)
    result, code = run("compute", run_dir)
    assert code in (0, 2)

    inputs = revenue_inputs()
    inputs["sections"][0]["statements"][0]["template"] = (
        "2026上半年公司实现营业收入 {rev:amount_yi}，同比增长 {yoy:percent2}。")
    inputs["sections"][0]["statements"][0]["bindings"]["rev"] = {"fact_id": "f-0001"}
    write_json_file(run_dir / "report_inputs.json", inputs)
    result, code = run("report", run_dir)
    assert code == 0, result
    assert result["quality_status"] == "verified"

    analysis = (run_dir / "analysis.md").read_text(encoding="utf-8")
    assert "# 测试公司（300000）2026分析" in analysis
    assert "营业收入 12.35 亿元" in analysis or "12.35亿元" in analysis

    review, review_code = run("review", run_dir)
    assert review_code == 0
    assert review["quality_status"] == "verified"
    assert review["report_validation"]["passed"] is True


def test_repair_chain_stops_within_budget(run_dir):
    """两轮失败修复仍在预算内；第三次新输入被拒，状态转为 maintenance_required。"""
    prepare_build_run(run_dir)
    base = {"schema_version": 1, "facts": [fact_input(raw_value="1.00")]}
    write_json_file(run_dir / "fact_inputs.json", base)
    _, code = run("compute", run_dir)
    assert code == 2

    base["facts"][0]["raw_value"] = "2.00"
    write_json_file(run_dir / "fact_inputs.json", base)
    _, code = run("compute", run_dir)
    assert code == 2

    base["facts"][0]["raw_value"] = "3.00"
    write_json_file(run_dir / "fact_inputs.json", base)
    _, code = run("compute", run_dir)
    assert code == 2

    base["facts"][0]["raw_value"] = "4.00"
    write_json_file(run_dir / "fact_inputs.json", base)
    result, code = run("compute", run_dir)
    assert code == 2
    assert result["quality_status"] == "maintenance_required"
    assert "budget exhausted" in result["issues"][0]
