"""daily_pick 单元测试。

覆盖：
- 4 条硬过滤规则（ST / 次新 / 市值 / 成交额）
- History 读写 / 冷却期 / 行业频次窗口
- rotate_pick 行业轮换算法
- Markdown 渲染（含风险标记）
- run_pipeline 主流程（mock 数据源）
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from daily_pick import (
    Candidate,
    History,
    PickConfig,
    PickRecord,
    build_markdown,
    filter_candidates,
    is_st_name,
    rotate_pick,
)


def _c(**kwargs) -> Candidate:
    defaults = {
        "code": "600519",
        "name": "贵州茅台",
        "market": "上海-主板",
        "total_mv_wan": 1_000_000.0,
        "amount_wan": 50_000.0,
        "pct_chg": 1.5,
        "listing_date": date(2001, 8, 27),
        "industry": "白酒",
    }
    defaults.update(kwargs)
    return Candidate(**defaults)


def _rec(date_str: str, code: str, industry: str = "x") -> PickRecord:
    return PickRecord(
        date=date_str, code=code, name="X", industry=industry, latest_report_url=""
    )


# ======================
# 硬过滤规则
# ======================


def test_filter_drops_st_name() -> None:
    today = date(2026, 8, 20)
    pool = [_c(name="ST 康美"), _c(name="*ST 信通"), _c(name="普通股")]
    assert [c.name for c in filter_candidates(pool, PickConfig(), today)] == ["普通股"]


def test_filter_drops_subnew_under_one_year() -> None:
    today = date(2026, 8, 20)
    fresh = _c(code="111", listing_date=today - timedelta(days=200))
    mature = _c(code="222", listing_date=today - timedelta(days=400))
    assert [c.code for c in filter_candidates([fresh, mature], PickConfig(), today)] == ["222"]


def test_filter_drops_low_market_cap() -> None:
    today = date(2026, 8, 20)
    tiny = _c(code="111", total_mv_wan=100_000.0)  # 10 亿
    big = _c(code="222", total_mv_wan=300_000.0)  # 30 亿
    assert [c.code for c in filter_candidates([tiny, big], PickConfig(), today)] == ["222"]


def test_filter_drops_low_amount() -> None:
    today = date(2026, 8, 20)
    cold = _c(code="111", amount_wan=2_000.0)
    warm = _c(code="222", amount_wan=3_000.0)
    assert [c.code for c in filter_candidates([cold, warm], PickConfig(), today)] == ["222"]


def test_is_st_recognises_variants() -> None:
    assert is_st_name("ST 康美") is True
    assert is_st_name("*ST 信通") is True
    assert is_st_name("退市股") is True
    assert is_st_name("贵州茅台") is False
    assert is_st_name("Stellantis") is False


# ======================
# History
# ======================


def test_history_corrupted_json_returns_empty(tmp_path) -> None:
    bad = tmp_path / "hist.json"
    bad.write_text("{not valid json", encoding="utf-8")
    assert History.load(bad).records == ()


def test_history_missing_file_returns_empty(tmp_path) -> None:
    assert History.load(tmp_path / "missing.json").records == ()


def test_history_roundtrip(tmp_path) -> None:
    path = tmp_path / "h.json"
    original = History(records=(_rec("2026-08-19", "600519", "白酒"),))
    original.save(path)
    loaded = History.load(path)
    assert loaded.records[0].code == "600519"
    assert loaded.records[0].industry == "白酒"


def test_history_is_in_cooldown() -> None:
    today = date(2026, 8, 20)
    recent = History(records=(_rec("2026-08-01", "600519", "白酒"),))
    assert recent.is_in_cooldown("600519", today, cooldown_days=30) is True
    old = History(records=(_rec("2026-07-15", "600519", "白酒"),))
    assert old.is_in_cooldown("600519", today, cooldown_days=30) is False


def test_history_industry_freq_window() -> None:
    today = date(2026, 8, 20)
    records = (
        _rec("2026-08-10", "a", "白酒"),
        _rec("2026-08-12", "b", "白酒"),
        _rec("2026-08-15", "c", "新能源"),
        _rec("2026-01-01", "d", "白酒"),
    )
    freq = History(records=records).industry_freq(today, window_days=14)
    assert freq == {"白酒": 2, "新能源": 1}


# ======================
# rotate_pick
# ======================


def test_rotate_prefers_fresh_industry() -> None:
    today = date(2026, 8, 20)
    candidates = [_c(code="a", industry="白酒"), _c(code="b", industry="新能源")]
    history = History(records=(_rec("2026-08-10", "x", "白酒"),))
    pick = rotate_pick(candidates, history, today, PickConfig(), random.Random(42))
    assert pick is not None
    assert pick.industry == "新能源"


def test_rotate_falls_back_to_min_freq_industry() -> None:
    today = date(2026, 8, 20)
    candidates = [_c(code="a", industry="白酒"), _c(code="c", industry="新能源")]
    history = History(records=(
        _rec("2026-08-10", "x", "白酒"),
        _rec("2026-08-11", "y", "白酒"),
        _rec("2026-08-12", "z", "新能源"),
    ))
    pick = rotate_pick(candidates, history, today, PickConfig(), random.Random(42))
    assert pick is not None
    assert pick.industry == "新能源"


def test_rotate_returns_none_when_all_in_cooldown() -> None:
    today = date(2026, 8, 20)
    candidates = [_c(code="a"), _c(code="b")]
    history = History(records=(_rec("2026-08-15", "a", "x"), _rec("2026-08-15", "b", "y")))
    pick = rotate_pick(candidates, history, today, PickConfig(), random.Random(42))
    assert pick is None


# ======================
# Markdown 渲染
# ======================


def test_markdown_no_pick_says_no_recommendation() -> None:
    md = build_markdown(None, today=date(2026, 8, 20))
    assert "无可推荐" in md


def test_markdown_contains_warn_flag_for_high_pct() -> None:
    pick = _c(pct_chg=5.5)
    md = build_markdown(pick, today=date(2026, 8, 20), freq={"白酒": 1})
    assert "⚠️" in md
    assert "600519" in md
    assert "白酒" in md


def test_markdown_no_warn_for_low_pct() -> None:
    md = build_markdown(_c(pct_chg=2.0), today=date(2026, 8, 20))
    assert "⚠️" not in md


def test_markdown_renders_report_link() -> None:
    """report_urls 元素 "YYYY-MM-DD 标题 URL" → 渲染 [标题（日期披露）](URL)。"""
    md = build_markdown(
        _c(),
        today=date(2026, 8, 20),
        report_urls=[
            "2026-04-28 2026年第一季度报告 http://www.cninfo.com.cn/q1",
            "2026-02-28 2025年年度报告 http://www.cninfo.com.cn/annual",
        ],
    )
    assert "[2026年第一季度报告（2026-04-28披露）](http://www.cninfo.com.cn/q1)" in md
    assert "[2025年年度报告（2026-02-28披露）](http://www.cninfo.com.cn/annual)" in md


def test_markdown_empty_report_shows_placeholder() -> None:
    md = build_markdown(_c(), today=date(2026, 8, 20), report_urls=[])
    assert "暂无披露计划" in md


# ======================
# 数据源层
# ======================


def test_determine_market() -> None:
    from daily_pick import _determine_market

    assert _determine_market("600519") == "上海-主板"
    assert _determine_market("688981") == "上海-科创板"
    assert _determine_market("000001") == "深圳-主板"
    assert _determine_market("300750") == "深圳-创业板"
    assert _determine_market("830799") == "北交所"
    assert _determine_market("999999") == ""


def test_parse_spot_row_known_stock_uses_old_listing_date() -> None:
    """CSV 收录的股票：listing_date = today - 730 天。"""
    import pandas as pd

    from daily_pick import parse_spot_row

    row = pd.Series({
        "代码": "sh600519",
        "名称": "贵州茅台",
        "成交额": 5_000_000_000.0,  # 元
        "涨跌幅": 1.5,
        "code6": "600519",
        "amount_wan": 500_000.0,
        "pct_chg": 1.5,
    })
    today = date(2026, 8, 20)
    cand = parse_spot_row(
        row,
        total_mv_yi=15_000.0,  # 1.5 万亿
        industry="白酒",
        is_listed=True,
        today=today,
    )
    assert cand is not None
    assert cand.code == "600519"
    assert cand.total_mv_wan == 150_000_000.0  # 1.5 万亿元 → 万元
    assert cand.amount_wan == 500_000.0
    assert cand.listing_date == today - timedelta(days=730)


def test_parse_spot_row_unknown_stock_marked_as_subnew() -> None:
    """未在 CSV 的股票：listing_date = today（被 365 天过滤剔除）。"""
    import pandas as pd

    from daily_pick import parse_spot_row

    row = pd.Series({
        "代码": "sh688825",
        "名称": "长鑫科技",
        "成交额": 1_000_000_000.0,
        "涨跌幅": 0.1,
        "code6": "688825",
        "amount_wan": 100_000.0,
        "pct_chg": 0.1,
    })
    today = date(2026, 8, 20)
    cand = parse_spot_row(
        row,
        total_mv_yi=1_000.0,
        industry="",
        is_listed=False,
        today=today,
    )
    assert cand is not None
    assert cand.listing_date == today


def test_parse_spot_row_invalid_code_returns_none() -> None:
    import pandas as pd

    from daily_pick import parse_spot_row

    row = pd.Series({
        "代码": "invalid",
        "名称": "x",
        "code6": "invalid",
        "amount_wan": 1.0,
        "pct_chg": 0.0,
    })
    today = date(2026, 8, 20)
    assert parse_spot_row(row, total_mv_yi=1.0, industry="x", is_listed=True, today=today) is None


def test_fetch_market_cap_via_tencent_parses() -> None:
    """mock 腾讯 HTTP 响应，断言解析正确。"""
    from daily_pick import fetch_market_cap_via_tencent

    fake_resp = (
        'v_sh600519="' + '~'.join(['x'] * 45) + '~16144.80";\n'
        'v_sz000001="' + '~'.join(['x'] * 45) + '~5000.00";\n'
    )

    class FakeResponse:
        text = fake_resp

        def raise_for_status(self) -> None: ...

    import daily_pick

    original = daily_pick.requests.get

    def fake_get(url, **kwargs):
        return FakeResponse()

    daily_pick.requests.get = fake_get  # type: ignore[assignment]
    try:
        cap = fetch_market_cap_via_tencent(["600519", "000001"])
    finally:
        daily_pick.requests.get = original  # type: ignore[assignment]

    assert cap == {"600519": 16144.80, "000001": 5000.00}


def test_fetch_hot_codes_returns_codes() -> None:
    """mock emappdata 响应。"""
    from daily_pick import fetch_hot_codes

    class FakeResponse:
        def raise_for_status(self) -> None: ...

        def json(self) -> dict:
            return {
                "data": [
                    {"sc": "SH600519", "rk": 1},
                    {"sc": "SZ000001", "rk": 2},
                ]
            }

    import daily_pick

    original = daily_pick.requests.post

    def fake_post(url, json=None, timeout=None):
        return FakeResponse()

    daily_pick.requests.post = fake_post  # type: ignore[assignment]
    try:
        codes = fetch_hot_codes()
    finally:
        daily_pick.requests.post = original  # type: ignore[assignment]

    assert codes == ["SH600519", "SZ000001"]


def test_fetch_real_listing_date_parses() -> None:
    """mock akshare stock_ipo_info 返回，断言解析上市日期。"""
    import pandas as pd

    from daily_pick import fetch_real_listing_date

    fake_df = pd.DataFrame({
        "item": ["上市地", "上市日期"],
        "value": ["深圳证券交易所", "2010-08-25"],
    })

    import akshare

    original = akshare.stock_ipo_info
    akshare.stock_ipo_info = lambda stock: fake_df  # type: ignore[assignment]
    try:
        result = fetch_real_listing_date("300109")
    finally:
        akshare.stock_ipo_info = original  # type: ignore[assignment]

    assert result == date(2010, 8, 25)


def test_fetch_real_listing_date_failure_returns_none() -> None:
    import akshare

    from daily_pick import fetch_real_listing_date

    def boom(stock):
        raise RuntimeError("network down")

    original = akshare.stock_ipo_info
    akshare.stock_ipo_info = boom  # type: ignore[assignment]
    try:
        result = fetch_real_listing_date("300109")
    finally:
        akshare.stock_ipo_info = original  # type: ignore[assignment]

    assert result is None


# ======================
# run_pipeline 主流程
# ======================


def _spot_row_new(code: str, name: str, amount_wan: float, pct: float = 1.0):
    """模拟 fetch_spot_all 后的行（含 code6 / amount_wan / pct_chg 派生列）。"""
    import pandas as pd

    return pd.Series({
        "代码": f"sh{code}" if code[0] in ("6", "9") else f"sz{code}",
        "名称": name,
        "成交额": amount_wan * 10_000,
        "涨跌幅": pct,
        "code6": code,
        "amount_wan": amount_wan,
        "pct_chg": pct,
    })


def test_run_pipeline_picks_one_and_appends_history() -> None:
    import pandas as pd

    from daily_pick import run_pipeline

    today = date(2026, 8, 20)
    spot = pd.DataFrame([
        _spot_row_new("600519", "贵州茅台", 1_000_000, 1.5),
        _spot_row_new("000001", "平安银行", 500_000, 0.8),
        _spot_row_new("300750", "宁德时代", 800_000, 2.1),
    ])
    cap_map = {"600519": 16_144.0, "000001": 5_000.0, "300750": 12_000.0}
    history = History()
    pick, md, new_history = run_pipeline(
        today,
        PickConfig(),
        history,
        random.Random(42),
        hot_codes=["SH600519", "SZ000001", "SZ300750"],
        spot_df=spot,
        cap_map=cap_map,
        report_urls=["2026-03-28 2025年年度报告 http://example.com/r.pdf"],
        real_listing_date=date(2001, 8, 27),
    )
    assert pick is not None
    assert pick.code in {"600519", "000001", "300750"}
    assert pick.code in md
    assert "2001-08-27" in md  # 真实上市日期注入后展示
    assert len(new_history.records) == 1
    assert new_history.records[0].code == pick.code


def test_run_pipeline_no_candidates_returns_none() -> None:
    import pandas as pd

    from daily_pick import run_pipeline

    today = date(2026, 8, 20)
    history = History()
    spot = pd.DataFrame()
    pick, md, _ = run_pipeline(
        today,
        PickConfig(),
        history,
        random.Random(42),
        hot_codes=[],
        spot_df=spot,
        cap_map={},
    )
    assert pick is None
    assert "无可推荐" in md


def test_run_pipeline_fetch_failure_does_not_raise() -> None:
    from daily_pick import run_pipeline

    today = date(2026, 8, 20)
    history = History()

    import daily_pick

    def boom():
        raise RuntimeError("network down")

    original = daily_pick.fetch_hot_codes
    daily_pick.fetch_hot_codes = boom  # type: ignore[assignment]
    try:
        pick, md, _ = run_pipeline(
            today, PickConfig(), history, random.Random(42)
        )
    finally:
        daily_pick.fetch_hot_codes = original  # type: ignore[assignment]

    assert pick is None
    assert "无可推荐" in md


def test_build_candidates_filters_via_spot() -> None:
    import pandas as pd

    from daily_pick import build_candidates

    today = date(2026, 8, 20)
    spot = pd.DataFrame([
        _spot_row_new("600519", "贵州茅台", 50_000),
        _spot_row_new("999999", "ST 测试", 50_000),
    ])

    import daily_pick

    daily_pick.fetch_spot_all = lambda: spot  # type: ignore[assignment]
    daily_pick.fetch_market_cap_via_tencent = lambda codes: {  # type: ignore[assignment]
        c: 15_000.0 for c in codes
    }
    # 让 ST 测试 code 也"已收录"，避免次新启发式剔除
    daily_pick.is_in_csv = lambda c: True  # type: ignore[assignment]
    daily_pick.fetch_industry_for_code = lambda c: "测试"  # type: ignore[assignment]

    candidates = build_candidates(
        ["SH600519", "SZ999999"], PickConfig(), today
    )
    # ST 测试被 ST 规则剔除，剩下贵州茅台
    assert [c.code for c in candidates] == ["600519"]


# ======================
# main() 端到端
# ======================


def test_main_dry_run_does_not_push(monkeypatch, capsys) -> None:
    import daily_pick

    monkeypatch.setattr(daily_pick, "fetch_hot_codes", list)
    monkeypatch.setenv("PUSH_MODE", "0")
    rc = daily_pick.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "无可推荐" in out
    assert "测试模式" in out


def test_main_push_mode_invokes_webhook(monkeypatch, tmp_path) -> None:
    import daily_pick

    captured: dict = {}

    class FakePusher:
        def __init__(self, webhook=None, keyword=None):
            captured["webhook"] = webhook
            captured["keyword"] = keyword

        def push_markdown(self, title, content):
            captured["title"] = title
            captured["content"] = content
            return True

    monkeypatch.setattr(daily_pick, "fetch_hot_codes", lambda: ["SH600519"])

    import pandas as pd

    spot = pd.DataFrame([_spot_row_new("600519", "贵州茅台", 50_000)])
    monkeypatch.setattr(daily_pick, "fetch_spot_all", lambda: spot)
    monkeypatch.setattr(daily_pick, "fetch_market_cap_via_tencent", lambda codes: {"600519": 16_144.0})
    monkeypatch.setattr(daily_pick, "is_in_csv", lambda c: True)
    monkeypatch.setattr(daily_pick, "fetch_industry_for_code", lambda c: "白酒")
    monkeypatch.setattr(daily_pick, "DingTalkPusher", FakePusher)
    monkeypatch.setenv("PUSH_MODE", "1")
    monkeypatch.setenv("DAILY_PICK_WEBHOOK", "https://oapi.dingtalk.com/robot/x")
    # 隔离真实 .env：HERMES_ENABLED=1 会让 main() 在推送后连真实 Hermes API
    monkeypatch.setenv("HERMES_ENABLED", "0")

    monkeypatch.setattr(daily_pick, "HISTORY_PATH", tmp_path / "h.json")
    rc = daily_pick.main()

    assert rc == 0
    assert captured["title"].startswith("【财报阅读】")
    assert "600519" in captured["content"]
    assert (tmp_path / "h.json").exists()  # history 已保存

def test_extract_announcement_id() -> None:
    from daily_pick import _extract_announcement_id

    url = (
        "http://www.cninfo.com.cn/new/disclosure/detail"
        "?stockCode=600539&announcementId=1225261054&orgId=gssh0600539"
    )
    assert _extract_announcement_id(url) == "1225261054"
    assert _extract_announcement_id("http://x.com/d?announcementId=abc") == "abc"
    assert _extract_announcement_id("not-a-url") == ""


def test_fetch_report_urls_builds_static_pdf_link(monkeypatch) -> None:
    """巨潮返回 detail 链接 → 应转成静态 PDF 直链；窗口内多条全收、按日期倒序。"""
    import pandas as pd

    import daily_pick

    def _detail(aid: str) -> str:
        return (
            "http://www.cninfo.com.cn/new/disclosure/detail"
            f"?stockCode=600539&announcementId={aid}&orgId=gssh0600539"
        )

    q1_df = pd.DataFrame({
        "代码": ["600539"],
        "简称": ["狮头股份"],
        "公告标题": ["2026年第一季度报告"],
        "公告时间": ["2026-04-30"],
        "公告链接": [_detail("1225261054")],
    })
    annual_df = pd.DataFrame({
        "代码": ["600539"],
        "简称": ["狮头股份"],
        "公告标题": ["2025年年度报告"],
        "公告时间": ["2026-03-28"],
        "公告链接": [_detail("1225260000")],
    })

    class FakeAk:
        @staticmethod
        def stock_zh_a_disclosure_report_cninfo(**kwargs):
            cat = kwargs.get("category")
            if cat == "一季报":
                return q1_df
            if cat == "年报":
                return annual_df
            return pd.DataFrame()

    monkeypatch.setitem(__import__("sys").modules, "akshare", FakeAk)
    # fetch_report_urls 内部 import akshare → 通过 sys.modules 注入 fake
    results = daily_pick.fetch_report_urls("600539")
    assert len(results) == 2
    assert results[0] == "2026-04-30 2026年第一季度报告 http://static.cninfo.com.cn/finalpage/2026-04-30/1225261054.PDF"
    assert results[1] == "2026-03-28 2025年年度报告 http://static.cninfo.com.cn/finalpage/2026-03-28/1225260000.PDF"


def test_run_pipeline_freq_includes_current_pick() -> None:
    """推送里展示的行业频次应包含本次推荐的行业（+1）。"""
    import pandas as pd

    from daily_pick import run_pipeline

    today = date(2026, 8, 20)
    spot = pd.DataFrame([
        _spot_row_new("600519", "贵州茅台", 50_000),
        _spot_row_new("000001", "平安银行", 30_000),
    ])
    cap_map = {"600519": 16_144.0, "000001": 5_000.0}
    # 历史已推过 通信设备
    history = History(records=(_rec("2026-08-19", "300308", "通信设备"),))
    pick, md, _ = run_pipeline(
        today,
        PickConfig(),
        history,
        random.Random(42),
        hot_codes=["SH600519", "SZ000001"],
        spot_df=spot,
        cap_map=cap_map,
        report_urls=[],
        real_listing_date=date(2001, 8, 27),
    )
    assert pick is not None
    # 频次行应含历史行业 + 本次行业（各 1 次）
    assert "通信设备: 1" in md
    assert f"{pick.industry}: 1" in md


def test_fetch_next_report_filters_past_dates(monkeypatch) -> None:
    """预约日 >= today 才返回；全过期返回空。"""
    import requests

    from daily_pick import fetch_next_report

    class FakeResp:
        def __init__(self, rows):
            self._rows = rows

        def raise_for_status(self) -> None: ...

        def json(self) -> dict:
            return {"result": {"data": self._rows}}

    def make_rows(dates: list[str]) -> list[dict]:
        return [
            {
                "REPORT_TYPE_NAME": "2026年 半年报",
                "APPOINT_PUBLISH_DATE": d,
            }
            for d in dates
        ]

    today = date(2026, 8, 21)
    # 案例1：最新预约日在未来 → 返回
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResp(make_rows(["2026-08-15", "2026-08-22"]))
    )
    assert fetch_next_report("000931", today) == "2026年 半年报（预约 2026-08-22 披露）"
    # 案例2：全部已过期 → 空
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResp(make_rows(["2026-08-15"]))
    )
    assert fetch_next_report("000931", today) == ""


def test_markdown_next_report_line() -> None:
    from daily_pick import build_markdown

    md = build_markdown(_c(), today=date(2026, 8, 21), next_report="2026年 半年报（预约 2026-08-22 披露）")
    assert "**下期财报**：2026年 半年报（预约 2026-08-22 披露）" in md

    md_no = build_markdown(_c(), today=date(2026, 8, 21))
    assert "下期财报" not in md_no
