"""黄金消息数据流、离线预览和官方GLD持仓回归测试。"""
from io import BytesIO

import pandas as pd
import pytest
import requests

from gold.analyzer import GoldAnalyzer
from gold.fed_expectations import build_report
from gold.formatter import build_gold_markdown, format_fed_expectations
from gold.holdings import parse_gld_archive, get_gld_holdings_history
from tests.test_gold_fed import NOW, record


def report():
    return build_report([record(), record("2026-09-28", 35.2, 64.8)], now=NOW, is_new_snapshot=True)


def gold_data():
    return {"time": "2026-09-29 16:00", "gold_price": 920.0,
            "xau_usd": 4140.0, "gold_rsi_14": 51, "simple_rsi_14": 49,
            "ali_rsi_14": None, "series": [], "fed_expectations": report()}


def test_formatter_shows_source_time_comparison_and_cumulative_meaning():
    text = format_fed_expectations(report())
    for value in ["70.9%", "+6.1", "2026-09-28", "2026-09-29", "金十", "北京时间", "累计", "2026-10-28"]:
        assert value in text
    assert "偏鹰" in text
    assert "基点" in text


def test_cached_fallback_stale_and_missing_messages_are_explicit():
    for status, label in [("cached", "快照未更新"), ("fallback", "获取失败或回退"), ("stale", "过期")]:
        r = build_report([record(), record("2026-09-28", 35.2, 64.8)], now=NOW, status=status)
        text = format_fed_expectations(r)
        assert label in text
        if status != "cached":
            assert "偏鹰" not in text
    text = format_fed_expectations({"status": "unavailable", "meetings": []})
    assert "暂缺" in text
    assert "降息 0" not in text


def test_prompt_has_facts_and_forbids_invented_macro_data():
    prompt = GoldAnalyzer(api_key="test")._build_prompt(gold_data())
    assert "70.9" in prompt
    assert "4140" in prompt
    assert "6.1" in prompt
    assert "不得编造" in prompt
    assert "美元指数" in prompt
    assert "较上一发布日期" in prompt
    assert "实际利率" in prompt


def test_message_handles_missing_international_quote():
    data = gold_data()
    data["xau_usd"] = None
    text = build_gold_markdown(data, "条件判断")
    assert "国际现货" in text and "暂缺" in text
    assert "美联储" in text and "条件判断" in text


def test_gold_first_message_and_compact_fed_appendix():
    text = build_gold_markdown(gold_data(), "分析正文")
    assert text.index("国内Au9999") < text.index("分析正文")
    assert "未来会议预期利率" not in text
    assert "Wilder RSI(14)" in text


def test_prompt_prioritizes_price_evidence_and_confirmation():
    prompt = GoldAnalyzer(api_key="test")._build_prompt(gold_data())
    assert "价格依据" in prompt
    assert "后续观察" in prompt
    assert "实时触及" in prompt
    assert "依次说明：利率预期" not in prompt


@pytest.mark.parametrize("status", ["fresh", "cached", "fallback", "stale", "awaiting_update", "unavailable"])
def test_compact_message_preserves_fed_reliability(status):
    data = gold_data()
    data["fed_expectations"]["status"] = status
    text = build_gold_markdown(data, "条件判断")
    assert "未来会议预期利率" not in text
    if status not in ("fresh", "cached"):
        assert "预期偏鹰" not in text
    else:
        assert "2026-09-28 06:00:00" in text


def test_stale_price_reference_is_labelled_and_close_range_not_ohlc():
    from gold.technicals import build_price_summary
    from tests.test_gold_technicals import candles
    data = gold_data()
    data["price_summary"] = build_price_summary(
        [{"D": r["D"], "C": r["C"]} for r in candles()], 121, today="2026-10-14")
    text = build_gold_markdown(data, "条件判断")
    assert "不判断当前技术趋势" in text
    assert "20交易日收盘区间" in text
    assert "2026-09-29" in text
    assert "20交易日高低区间" not in text


def test_full_candles_feed_summary_and_rsi_before_analysis(monkeypatch):
    from datetime import datetime
    import gold.data_fetcher as fetcher
    from tests.test_gold_technicals import candles
    rows = candles()[::-1] + [{"D": "2026-09-30", "C": 999}]
    monkeypatch.setattr(fetcher, "china_now", lambda: datetime.fromisoformat("2026-09-30T16:00:00+08:00"))
    monkeypatch.setattr(fetcher, "get_gold_kline_data", lambda: rows)
    monkeypatch.setattr(fetcher, "get_gold_price_now", lambda: 121)
    monkeypatch.setattr(fetcher, "get_xau_usd_price", lambda: 4140)
    monkeypatch.setattr(fetcher, "get_fed_expectations", report)
    monkeypatch.setattr(fetcher, "get_ali_rsi", lambda: None)
    monkeypatch.setattr(fetcher, "get_vix_series", lambda: [])
    monkeypatch.setattr(fetcher, "get_gld_holdings_history", lambda: [
        {"Date": "2026-09-25", "gold_tonnes": 1000}, {"Date": "2026-09-29", "gold_tonnes": 998}])
    data = fetcher.get_merged_gold_data()
    assert data["price_summary"]["ma20"] == 110.5
    assert data["gold_rsi_14"] == 100
    assert data["holdings_summary"]["change_tonnes"] == -2
    latest = next(row for row in data["series"] if row["Date"] == "2026-09-29")
    assert latest["gold_tonnes_change"] == -2
    prompt = GoldAnalyzer(api_key="test")._build_prompt(data)
    assert "110.5" in prompt and "2026-09-25" in prompt


def workbook(rows):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame({"notice": ["archive"]}).to_excel(writer, sheet_name="Disclaimer", index=False)
        pd.DataFrame(rows).to_excel(writer, sheet_name="US GLD Historical Archive", index=False)
    return out.getvalue()


def test_official_holdings_are_used_directly_without_price_conversion():
    content = workbook({"Date": ["25-Sep-2026", "28-Sep-2026", "24-Sep-2026"],
                        "Tonnes of Gold": [1000.5, 1004.7, 998],
                        "Total Net Asset Value in the Trust": [1, 999999, 20]})
    rows = parse_gld_archive(content, days=2)
    assert rows == [{"Date": "2026-09-28", "gold_tonnes": 1004.7},
                    {"Date": "2026-09-25", "gold_tonnes": 1000.5}]


def test_gld_missing_tonnes_column_does_not_estimate_from_assets():
    content = workbook({"Date": ["28-Sep-2026"], "Total Net Asset Value in the Trust": [9999999]})
    with pytest.raises(ValueError):
        parse_gld_archive(content)


def test_gld_skips_unusable_rows():
    content = workbook({"Date": ["bad", "28-Sep-2026", "25-Sep-2026", "24-Sep-2026"],
                        "Tonnes of Gold": [1000, float("nan"), -1, 998]})
    assert parse_gld_archive(content) == [{"Date": "2026-09-24", "gold_tonnes": 998}]


def test_gld_network_failure_is_optional(monkeypatch):
    import gold.holdings as holdings
    def fail(*args, **kwargs):
        raise requests.Timeout("timeout")
    monkeypatch.setattr(holdings.requests, "get", fail)
    assert get_gld_holdings_history() == []


def test_merged_data_includes_fed_and_xau_and_published_holdings(monkeypatch):
    import gold.data_fetcher as fetcher
    monkeypatch.setattr(fetcher, "get_gld_holdings_history", lambda: [
        {"Date": "2026-09-25", "gold_tonnes": 1000.5}, {"Date": "2026-09-28", "gold_tonnes": 1004.7}])
    monkeypatch.setattr(fetcher, "get_gld_assets_history", lambda: pytest.fail("must not estimate holdings from assets"))
    monkeypatch.setattr(fetcher, "get_fed_expectations", report)
    monkeypatch.setattr(fetcher, "get_xau_usd_price", lambda: 4140)
    monkeypatch.setattr(fetcher, "get_gold_price_now", lambda: 920)
    monkeypatch.setattr(fetcher, "get_gold_kline_data", lambda: [])
    monkeypatch.setattr(fetcher, "get_vix_series", lambda: [])
    monkeypatch.setattr(fetcher, "get_ali_rsi", lambda: None)
    result = fetcher.get_merged_gold_data()
    assert result["xau_usd"] == 4140
    assert result["fed_expectations"]["meetings"][0]["hike_pct"] == 70.9
    assert result["series"][0]["gold_tonnes_change"] == pytest.approx(4.2)
    def fail():
        raise requests.Timeout("timeout")
    monkeypatch.setattr(fetcher, "get_xau_usd_price", fail)
    assert fetcher.get_merged_gold_data()["xau_usd"] is None


def test_dry_run_prints_full_message_without_sending(monkeypatch, capsys):
    import sys

    import gold_price_push as main
    monkeypatch.setattr(sys, "argv", ["gold_price_push.py"])
    monkeypatch.setenv("PUSH_MODE", "0")
    monkeypatch.setattr(main, "get_merged_gold_data", gold_data)
    monkeypatch.setattr(main, "GoldAnalyzer", lambda: type("FakeAnalyzer", (), {"analyze": lambda self, data: "分析正文"})())
    monkeypatch.setattr(main, "DingTalkPusher", lambda **kw: pytest.fail("must not initialize a real pusher"))
    main.main()
    output = capsys.readouterr().out
    assert "70.9%" in output and "分析正文" in output and "国际现货" in output
