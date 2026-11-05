import json
from decimal import Decimal

import pytest
from artifacts import emit_status, read_json, write_json


def test_write_and_read_utf8_chinese_json(run_dir):
    target = run_dir / "doc.json"
    value = {"company": "贵州茅台", "报告类型": "年度报告"}
    write_json(target, value)
    raw = target.read_text(encoding="utf-8")
    assert "贵州茅台" in raw
    assert read_json(target) == value


def test_decimal_serialized_as_string(run_dir):
    target = run_dir / "amounts.json"
    write_json(target, {"value": Decimal("12345000.00")})
    data = read_json(target)
    assert data["value"] == "12345000.00"


def test_atomic_write_failure_keeps_existing_file(run_dir, monkeypatch):
    import artifacts

    target = run_dir / "keep.json"
    write_json(target, {"version": 1})
    original = target.read_bytes()

    def broken_replace(src, dst):
        raise OSError("interrupted")

    monkeypatch.setattr(artifacts.os, "replace", broken_replace)
    with pytest.raises(OSError):
        write_json(target, {"version": 2})
    assert target.read_bytes() == original


def test_emit_status_prints_single_json_line(capsys):
    emit_status("ok", {"structured_financials": "run/structured_financials.json"}, [])
    captured = capsys.readouterr()
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload == {
        "status": "ok",
        "artifacts": {"structured_financials": "run/structured_financials.json"},
        "issues": [],
    }


def test_emit_status_includes_issues(capsys):
    emit_status("partial", {}, ["2024-06-30/income: no_data"])
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "partial"
    assert payload["issues"] == ["2024-06-30/income: no_data"]
