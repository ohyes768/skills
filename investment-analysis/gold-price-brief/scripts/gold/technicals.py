"""国内黄金日线归一化及价格摘要；仅计算已完成交易日。"""
from datetime import date
from math import isfinite


def positive_number(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


def normalize_candles(rows, *, today):
    """同日一致记录去重，冲突记录全部剔除，返回升序日线和提示。"""
    cutoff = date.fromisoformat(str(today)[:10])
    by_day, conflicts, warnings = {}, set(), []
    for row in rows or []:
        try:
            day = date.fromisoformat(str(row["D"])[:10])
            close = positive_number(row.get("C"))
            if close is None:
                raise ValueError("无效收盘价")
        except (KeyError, TypeError, ValueError):
            warnings.append("已剔除无效日线")
            continue
        if day >= cutoff:
            continue
        high, low = positive_number(row.get("H")), positive_number(row.get("L"))
        if high is None or low is None or not low <= close <= high:
            high, low = None, None
        candle = {"D": day.isoformat(), "C": close, "H": high, "L": low}
        if day in by_day and by_day[day] != candle:
            conflicts.add(day)
            warnings.append(f"{day}日线冲突，已剔除")
        by_day[day] = candle
    return [by_day[day] for day in sorted(by_day) if day not in conflicts], list(dict.fromkeys(warnings))


def build_price_summary(rows, quote, *, today):
    candles, warnings = normalize_candles(rows, today=today)
    result = dict.fromkeys([
        "last_close", "last_close_date", "previous_close_date", "day_change_pct",
        "five_day_start_date", "five_day_change_pct", "quote_change_pct", "ma5", "ma20",
        "range_start_date", "range_end_date", "range_low", "range_high", "range_kind",
    ])
    result.update(status="unavailable", sample_count=len(candles), range_count=0,
                  unit="元/克", warnings=warnings)
    if not candles:
        return result
    closes = [row["C"] for row in candles]
    latest = candles[-1]
    age = (date.fromisoformat(str(today)[:10]) - date.fromisoformat(latest["D"])).days
    result.update(status="stale" if age > 7 else "fresh",
                  last_close=closes[-1], last_close_date=latest["D"])
    if age > 7:
        warnings.append("日线超过7个自然日，仅供历史参考")
    change = lambda current, baseline: (current / baseline - 1) * 100
    valid_quote = positive_number(quote)
    if valid_quote is not None:
        result["quote_change_pct"] = change(valid_quote, closes[-1])
    if len(closes) >= 2:
        result.update(day_change_pct=change(closes[-1], closes[-2]), previous_close_date=candles[-2]["D"])
    if len(closes) >= 6:
        result.update(five_day_change_pct=change(closes[-1], closes[-6]), five_day_start_date=candles[-6]["D"])
    for window in (5, 20):
        if len(closes) >= window:
            result[f"ma{window}"] = sum(closes[-window:]) / window
    window = candles[-20:]
    complete = len(window) == 20 and all(row["H"] is not None and row["L"] is not None for row in window)
    result.update(range_count=len(window), range_start_date=window[0]["D"], range_end_date=window[-1]["D"],
                  range_kind="高低区间" if complete else "收盘区间",
                  range_low=min(row["L"] if complete else row["C"] for row in window),
                  range_high=max(row["H"] if complete else row["C"] for row in window))
    return result


def build_holdings_summary(rows, *, today):
    """只在官方有效持仓记录间比较，不受金价/VIX记录插入影响。"""
    valid = {}
    for row in rows or []:
        try:
            day = date.fromisoformat(row["Date"])
            tonnes = positive_number(row.get("gold_tonnes"))
        except (KeyError, TypeError, ValueError):
            continue
        if tonnes is not None and day < date.fromisoformat(str(today)[:10]):
            valid[day.isoformat()] = tonnes
    dates = sorted(valid)
    if not dates:
        return {"status": "unavailable"}
    latest = dates[-1]
    result = {"date": latest, "tonnes": valid[latest], "change_tonnes": None, "baseline_date": None,
              "status": "stale" if (date.fromisoformat(str(today)[:10]) - date.fromisoformat(latest)).days > 7 else "fresh"}
    if len(dates) > 1:
        result.update(baseline_date=dates[-2], change_tonnes=round(valid[latest] - valid[dates[-2]], 2))
    return result
