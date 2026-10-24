"""Normalize one snapshot into a JSON report and plain Chinese Markdown."""

import math
from datetime import datetime, timedelta

from providers import (
    AIR_URL,
    LATITUDE,
    LONGITUDE,
    SHANGHAI,
    WEATHER_UNITS,
    WEATHER_URL,
    hourly_rows,
    local_time,
    select_observations,
)


def average(values):
    return round(sum(values) / len(values), 2) if values else None


def weather_summary(rows):
    values = {k: [r[k] for r in rows if r[k] is not None] for k in WEATHER_UNITS}
    counts = {k: len(v) for k, v in values.items()}
    wind = [
        (r["wind_direction_10m"], r["wind_speed_10m"])
        for r in rows
        if r["wind_direction_10m"] is not None and r["wind_speed_10m"] is not None
    ]
    x = sum(math.cos(math.radians(d)) * s for d, s in wind)
    y = sum(math.sin(math.radians(d)) * s for d, s in wind)
    weight = sum(s for _, s in wind)
    direction = (
        round(math.degrees(math.atan2(y, x)) % 360, 1) % 360
        if weight and math.hypot(x, y) / weight >= 0.3
        else None
    )
    joint = lambda r, field, threshold: (
        r[field] is not None
        and r[field] < threshold
        and r["wind_speed_10m"] is not None
        and r["wind_speed_10m"] < 2
    )
    return {
        "counts": counts,
        "wind_speed_mean_ms": average(values["wind_speed_10m"]),
        "wind_direction_deg": direction,
        "precipitation_sum_mm": round(sum(values["precipitation"]), 2)
        if values["precipitation"]
        else None,
        "rain_hours": sum(v >= 0.1 for v in values["precipitation"]),
        "humidity_mean_pct": average(values["relative_humidity_2m"]),
        "temperature_min_c": min(values["temperature_2m"], default=None),
        "temperature_max_c": max(values["temperature_2m"], default=None),
        "boundary_layer_mean_m": average(values["boundary_layer_height"]),
        "calm_hours": sum(v < 2 for v in values["wind_speed_10m"]),
        "humid_calm_hours": sum(
            r["relative_humidity_2m"] is not None
            and r["relative_humidity_2m"] >= 80
            and r["wind_speed_10m"] is not None
            and r["wind_speed_10m"] < 2
            for r in rows
        ),
        "low_mixing_calm_hours": sum(
            joint(r, "boundary_layer_height", 300) for r in rows
        ),
    }


def explain_weather(w):
    factors = []
    if w["calm_hours"] >= 6:
        factors.append(f"有 {w['calm_hours']} 小时风速低于 2 m/s，污染物较容易积住。")
    if w["humid_calm_hours"] >= 4:
        factors.append(
            f"有 {w['humid_calm_hours']} 小时同时高湿（≥80%）且风小，可能促进颗粒物增长。"
        )
    if w["low_mixing_calm_hours"] >= 4:
        factors.append(
            f"有 {w['low_mixing_calm_hours']} 小时边界层低于 300 m 且风小，向上扩散的空间较小；这不等于已经诊断出逆温。"
        )
    if w["rain_hours"] >= 3 and w["precipitation_sum_mm"] >= 2:
        factors.append(
            f"有效时段有 {w['rain_hours']} 小时降水、累计 {w['precipitation_sum_mm']:g} mm，通常有利于清除颗粒物。"
        )
    if w["wind_speed_mean_ms"] is not None and w["wind_speed_mean_ms"] >= 3:
        factors.append(
            f"有效时段平均风速 {w['wind_speed_mean_ms']:g} m/s，通常利于扩散，但也可能带来上风向污染。"
        )
    return factors


def build_report(snapshot, now=None, days=5):
    if not isinstance(snapshot, dict):
        raise TypeError("输入快照必须是 JSON 对象")
    if days not in range(1, 6):
        raise ValueError("days 必须为 1–5")
    now = now or datetime.now(SHANGHAI)
    if now.tzinfo is None:
        raise ValueError("报告时间必须包含时区")
    now = now.astimezone(SHANGHAI)
    warnings = []
    errors = snapshot.get("errors", {})
    if not isinstance(errors, dict):
        raise TypeError("快照 errors 必须是对象")
    for key, error in errors.items():
        warnings.append(f"{key} 获取失败：{error}")
    fetched_at = snapshot.get("fetched_at")
    if fetched_at:
        fetched = local_time(fetched_at)
        if now - fetched > timedelta(hours=3):
            warnings.append("输入快照已超过3小时，属于旧批次；预报也可能已经更新。")
        if fetched > now + timedelta(minutes=5):
            warnings.append("快照获取时间晚于报告时间，请核对回放时间。")
    series = {}
    for key in ("air", "weather"):
        try:
            series[key] = hourly_rows(snapshot[key], key)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            series[key] = {}
            warnings.append(f"{key} 无可用逐小时数据：{exc}")
    try:
        observations = select_observations(snapshot.get("observations"), now)
    except (ValueError, TypeError) as exc:
        observations = select_observations(None, now)
        warnings.append(f"实测数据格式错误：{exc}")
    current = None
    if observations["status"] == "available":
        current = {
            "kind": "observation",
            "pm25": observations["mean_pm25"],
            "time": observations["observed_at"],
            "source": observations["source"],
            "description": observations["aggregation"],
        }
    else:
        warnings.append(
            "实测已过期，仅保留为历史参考。"
            if observations["status"] == "stale"
            else "未取得可用实测，当前情况只能参考模型估计。"
        )
        available = [
            (t, r["pm2_5"])
            for t, r in series["air"].items()
            if now - timedelta(hours=2) <= t <= now and r["pm2_5"] is not None
        ]
        if available:
            t, value = max(available)
            current = {
                "kind": "model_estimate",
                "pm25": value,
                "time": t.isoformat(),
                "source": "Open-Meteo / CAMS Global",
                "description": "模型估计，非站点实测",
            }
    daily = []
    for offset in range(days):
        date = (now + timedelta(days=offset)).date()
        air = sorted(
            (t, r["pm2_5"])
            for t, r in series["air"].items()
            if t.date() == date and r["pm2_5"] is not None
        )
        remaining = [(t, v) for t, v in air if t >= now]
        weather = weather_summary(
            [r for t, r in series["weather"].items() if t.date() == date]
        )
        row = {
            "date": date.isoformat(),
            "expected_hours": 24,
            "valid_hours": len(air),
            "complete": len(air) == 24,
            "valid_start": air[0][0].isoformat() if air else None,
            "valid_end": air[-1][0].isoformat() if air else None,
            "mean_pm25": average([v for _, v in air]),
            "peak_pm25": max((v for _, v in air), default=None),
            "peak_times": [
                t.isoformat() for t, v in air if v == max(v for _, v in air)
            ],
            "remaining_hours": len(remaining),
            "remaining_mean_pm25": average([v for _, v in remaining]),
            "weather": weather,
            "factors": explain_weather(weather),
        }
        daily.append(row)
        if not row["complete"]:
            warnings.append(
                f"{date} PM2.5 仅 {len(air)}/24 小时有效，不能当作完整日均。"
            )
        missing = [k for k, n in weather["counts"].items() if n < 24]
        if missing:
            warnings.append(
                f"{date} 天气要素不足24小时：{', '.join(missing)}；解释仅针对有效时段。"
            )
    candidates = [d for d in daily if d["valid_hours"] >= 18]
    trend = {
        "lowest_date": None,
        "highest_date": None,
        "description": "有效数据不足，暂不比较每天高低。",
    }
    if len(candidates) >= 2:
        low = min(candidates, key=lambda d: d["mean_pm25"])
        high = max(candidates, key=lambda d: d["mean_pm25"])
        text = (
            "各日模型均值相同，暂无明显高低差别。"
            if low["mean_pm25"] == high["mean_pm25"]
            else f"按有效时段模型均值比较，{low['date']} 最低（{low['mean_pm25']:g}），{high['date']} 最高（{high['mean_pm25']:g} μg/m³）。"
        )
        trend.update(
            lowest_date=low["date"], highest_date=high["date"], description=text
        )
    usable = current is not None or any(d["valid_hours"] for d in daily)
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(timespec="seconds"),
        "input_fetched_at": fetched_at,
        "timezone": "Asia/Shanghai",
        "location": {
            "name": "杭州主城区参考点",
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
        },
        "status": "unavailable" if not usable else "partial" if warnings else "ok",
        "unit": "μg/m³",
        "current": current,
        "observations": observations,
        "daily": daily,
        "trend": trend,
        "warnings": warnings,
        "sources": {
            "air": AIR_URL,
            "weather": WEATHER_URL,
            "observations": observations["source_url"],
            "model_initialization_time": None,
        },
        "limitations": [
            "含今天的自然日预报，不代表从现在起完整120小时；今天全天模型值含已过时段。",
            "CAMS Global 是约45km网格模型，不能代表某条街道；尚未在杭州进行本地精度回测。",
            "气象解释是条件性线索，不是另一个浓度预测模型；缺少上风向污染数据，不能判断区域输送。",
            "仅比较PM2.5浓度，不换算AQI或污染等级，不代表全部污染物的空气质量。",
        ],
        "attribution": "实测：中国环境监测总站；空气质量模型：CAMS / ECMWF，经 Open-Meteo 提供；天气：Open-Meteo。",
    }


def render_markdown(report):
    fmt = lambda v: "缺失" if v is None else f"{v:g}"
    lines = [
        "# 杭州 PM2.5：现在与未来几天",
        "",
        f"生成时间：{report['generated_at']}（北京时间）",
        "",
    ]
    current = report["current"]
    if current:
        label = "站点实测" if current["kind"] == "observation" else "模型估计，非实测"
        lines += [
            f"现在参考：**{fmt(current['pm25'])} μg/m³**（{label}，数据时间 {current['time']}）。",
            current["description"] + "。",
            "",
        ]
    else:
        lines += ["当前 PM2.5 暂无可用数据。", ""]
    obs = report["observations"]
    if obs["stations"]:
        values = [s["pm25"] for s in obs["stations"]]
        lines += [
            f"同一小时共 {len(values)} 个站点，范围 {fmt(min(values))}–{fmt(max(values))} μg/m³；"
            + (
                "这批实测已过期。"
                if obs["status"] == "stale"
                else "各站点有差异，不能代表家门口。"
            ),
            "",
        ]
    lines += [
        report["trend"]["description"],
        "比较仅使用至少18小时有效的日期；不完整日期仍可能影响排序。",
        "",
        "| 日期 | 模型均值 μg/m³ | 小时峰值 μg/m³ | 有效小时 |",
        "|---|---:|---:|---:|",
    ]
    for d in report["daily"]:
        lines.append(
            f"| {d['date']} | {fmt(d['mean_pm25'])} | {fmt(d['peak_pm25'])} | {d['valid_hours']}/24 |"
        )
    first = report["daily"][0]
    lines += [
        "",
        "表中均为模型值；不满24小时的是有效时段均值。今天全天值包含已经过去的时段。",
        f"今天从生成时间之后还剩 {first['remaining_hours']} 个有效整点，模型均值 {fmt(first['remaining_mean_pm25'])} μg/m³。",
        "",
        "天气怎么影响它（以下为条件性线索，不是确定成因；按当天各天气要素的有效小时统计，覆盖可能与PM2.5不同）：",
        "",
    ]
    directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    for d in report["daily"]:
        w = d["weather"]
        direction = (
            directions[int((w["wind_direction_deg"] + 22.5) // 45) % 8]
            if w["wind_direction_deg"] is not None
            else "缺失/多变/静风"
        )
        lines += [
            f"- **{d['date']}**：平均风速 {fmt(w['wind_speed_mean_ms'])} m/s，风向 {direction}；"
            f"降水累计 {fmt(w['precipitation_sum_mm'])} mm；平均湿度 {fmt(w['humidity_mean_pct'])}%；"
            f"温度 {fmt(w['temperature_min_c'])}–{fmt(w['temperature_max_c'])}℃。"
            + (
                " ".join(d["factors"])
                or "现有数据未触发明显气象提示，不代表一定好或差。"
            )
        ]
    lines += [
        "",
        "温度本身不能直接判断PM2.5高低；风向要结合上风向污染，不能认定某个方向的风一定干净。",
        "",
    ]
    if obs["stations"]:
        lines += ["站点明细（" + str(obs["observed_at"]) + "）：", ""]
        lines += [
            f"- {s['name']}（{s['code']}）：{fmt(s['pm25'])} μg/m³，距参考点 {s['distance_km']:g} km。"
            for s in obs["stations"]
        ]
        lines.append("")
    if report["warnings"]:
        lines += ["数据提示：", ""] + [f"- {w}" for w in report["warnings"]] + [""]
    lines += ["使用边界：", ""] + [f"- {s}" for s in report["limitations"]]
    lines += [
        "",
        report["attribution"],
        "来源：[中国环境监测总站](https://www.cnemc.cn/)、[Open-Meteo 空气质量](https://open-meteo.com/en/docs/air-quality-api)、[Open-Meteo 天气](https://open-meteo.com/en/docs)。",
        "",
    ]
    return "\n".join(lines)
