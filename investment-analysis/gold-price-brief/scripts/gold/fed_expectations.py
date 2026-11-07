"""金十快照归一化与利率预期计算（无网络、无模型推断）。"""
from datetime import date, datetime, timedelta, timezone
import math
import re

SHANGHAI = timezone(timedelta(hours=8))
SOURCE_URL = "https://www.jin10.com/minipro/index.html#/pages_sub/longPic/stockLongPic?category=interestRateForecast&attr_id=0&type=1"
MAX_AGE_HOURS = 96


def china_now(now=None):
    """无时区的测试/调用时间按北京时间解释，不依赖服务器时区。"""
    now = now or datetime.now(SHANGHAI)
    return now.replace(tzinfo=SHANGHAI) if now.tzinfo is None else now.astimezone(SHANGHAI)


def _rate_range(value):
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*(?:\(Current\))?\s*", value)
    if not match:
        raise ValueError("无效利率区间")
    lower, upper = map(int, match.groups())
    if not 0 <= lower < upper <= 3000 or upper - lower != 25:
        raise ValueError("利率区间应为25个基点")
    return [lower, upper]


def _probability(value):
    if not isinstance(value, str) or not value.endswith("%"):
        raise ValueError("概率缺失或格式错误")
    number = float(value[:-1])
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValueError("概率超出范围")
    return number


def normalize_record(record, *, now=None):
    """只使用 resData 当前列；禁止把缺失概率解释为零。"""
    try:
        if record.get("category") != "interestRateForecast":
            raise ValueError("非利率预测记录")
        published = datetime.strptime(record["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
        if published > china_now(now) + timedelta(minutes=5):
            raise ValueError("发布时间在未来")
        raw_meetings = record["data"]["json"]["resData"]
        if not isinstance(raw_meetings, list) or not raw_meetings:
            raise ValueError("会议数据缺失")
        current = _rate_range(raw_meetings[0]["target_rate"])
        meetings = []
        seen = set()
        for raw in raw_meetings:
            meeting_date = date.fromisoformat(raw["date"])
            if meeting_date.isoformat() in seen or meeting_date < published.date():
                raise ValueError("会议日期重复或早于快照")
            seen.add(meeting_date.isoformat())
            if raw.get("target_rate") and _rate_range(raw["target_rate"]) != current:
                raise ValueError("当前利率不一致")
            distribution = []
            ranges = set()
            for row in raw["data"]:
                if row["name"] == "date":
                    if date.fromisoformat(row["value"][0]) != published.date():
                        raise ValueError("概率观察日期与快照不符")
                    continue
                bounds = _rate_range(row["name"])
                if "Current" in row["name"] and bounds != current:
                    raise ValueError("当前利率标记不一致")
                if tuple(bounds) in ranges:
                    raise ValueError("重复利率区间")
                ranges.add(tuple(bounds))
                distribution.append({"lower_bps": bounds[0], "upper_bps": bounds[1],
                                     "probability_pct": _probability(row["value"][0])})
            total = sum(r["probability_pct"] for r in distribution)
            # 金十保留一位小数，允许每档0.05个百分点的舍入误差。
            if not distribution or abs(total - 100) > min(0.5, len(distribution) * 0.051):
                raise ValueError("概率总和不接近100%")
            for r in distribution:
                if r["lower_bps"] < current[1] and r["upper_bps"] > current[0] and [r["lower_bps"], r["upper_bps"]] != current:
                    raise ValueError("利率档位与当前区间重叠")
            cut = sum(r["probability_pct"] for r in distribution if r["upper_bps"] <= current[0])
            hold = sum(r["probability_pct"] for r in distribution if r["lower_bps"] == current[0])
            hike = sum(r["probability_pct"] for r in distribution if r["lower_bps"] >= current[1])
            expected_bps = sum((r["lower_bps"] + r["upper_bps"]) / 2 * r["probability_pct"] for r in distribution) / total
            meetings.append({"meeting_date": meeting_date.isoformat(), "distribution": distribution,
                             "cut_pct": round(cut, 2), "hold_pct": round(hold, 2), "hike_pct": round(hike, 2),
                             "expected_rate_pct": round(expected_bps / 100, 6),
                             "expected_change_bps": round(expected_bps - sum(current) / 2, 4)})
        return {"published_at": published.isoformat(), "current_target_bps": current,
                "meetings": sorted(meetings, key=lambda m: m["meeting_date"])}
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("利率快照结构错误") from exc


def valid_records(records, *, now=None):
    """每个北京时间发布日期保留最新有效快照，返回原始记录。"""
    by_day = {}
    if not isinstance(records, list):
        return []
    for raw in records:
        try:
            snap = normalize_record(raw, now=now)
        except ValueError:
            continue
        day = snap["published_at"][:10]
        if day not in by_day or raw["time"] > by_day[day]["time"]:
            by_day[day] = raw
    return sorted(by_day.values(), key=lambda r: r["time"], reverse=True)[:180]


def build_report(records, *, now=None, status="fresh", is_new_snapshot=False):
    """比较同一会议、相同当前目标利率的前一发布日期快照。"""
    now = china_now(now)
    snapshots = [normalize_record(r, now=now) for r in valid_records(records, now=now)]
    report = {"source": "金十数据·美联储利率预测", "source_url": SOURCE_URL,
              "status": "unavailable", "published_at": None, "meetings": [],
              "is_new_snapshot": is_new_snapshot, "warnings": []}
    if not snapshots:
        return report
    latest = snapshots[0]
    age = (now - datetime.fromisoformat(latest["published_at"])).total_seconds() / 3600
    report.update(published_at=latest["published_at"], current_target_bps=latest["current_target_bps"],
                  age_hours=round(age, 1), status=status)
    if age > MAX_AGE_HOURS:
        report["status"] = "stale"
    # 数据源未滚动时不能沿用旧的当前目标利率；同日保守停用。
    if any(m["meeting_date"] <= now.date().isoformat() for m in latest["meetings"]):
        report["status"] = "awaiting_update"
        return report
    for meeting in latest["meetings"][:3]:
        meeting = dict(meeting, change=None, direction="unknown")
        for previous in snapshots[1:]:
            candidate = next((m for m in previous["meetings"] if m["meeting_date"] == meeting["meeting_date"]), None)
            if candidate is None:
                continue
            if previous["current_target_bps"] != latest["current_target_bps"]:
                break
            meeting["change"] = {
                "baseline_published_at": previous["published_at"],
                "cut_pp": round(meeting["cut_pct"] - candidate["cut_pct"], 2),
                "hold_pp": round(meeting["hold_pct"] - candidate["hold_pct"], 2),
                "hike_pp": round(meeting["hike_pct"] - candidate["hike_pct"], 2),
                "expected_rate_bps": round((meeting["expected_rate_pct"] - candidate["expected_rate_pct"]) * 100, 4),
            }
            delta = meeting["change"]["expected_rate_bps"]
            if report["status"] in ("fresh", "cached"):
                meeting["direction"] = "hawkish" if delta > 0.1 else "dovish" if delta < -0.1 else "unchanged"
            break
        report["meetings"].append(meeting)
    return report
