"""Public data adapters for Hangzhou; Python standard library only."""

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")
LATITUDE, LONGITUDE = 30.2741, 120.1551
RADIUS_KM = 25
CNEMC_URL = "https://air.cnemc.cn:18007/HourChangesPublish/GetAllAQIPublishLive"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_UNITS = {
    "temperature_2m": "°C",
    "relative_humidity_2m": "%",
    "precipitation": "mm",
    "wind_speed_10m": "m/s",
    "wind_direction_10m": "°",
    "boundary_layer_height": "m",
}


def number(value, minimum=0):
    """Accept zero, reject missing sentinels, booleans and nonfinite values."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return (
        result
        if math.isfinite(result) and (minimum is None or result >= minimum)
        else None
    )


def local_time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("时间必须包含时区偏移，例如 +08:00")
    return result.astimezone(SHANGHAI)


def is_hangzhou(row):
    if not isinstance(row, dict):
        return False
    code = row.get("CityCode")
    return str(code) == "330100" or (
        code is None and row.get("Area") in ("杭州", "杭州市")
    )


def distance_km(lat, lon):
    p1, p2 = math.radians(LATITUDE), math.radians(lat)
    a = math.sin((p2 - p1) / 2) ** 2
    a += math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon - LONGITUDE) / 2) ** 2
    return 6371 * 2 * math.asin(min(1, math.sqrt(a)))


def select_observations(rows, now):
    result = {
        "status": "unavailable",
        "source": "中国环境监测总站 CNEMC",
        "source_url": CNEMC_URL,
        "observed_at": None,
        "mean_pm25": None,
        "mean_pm25_24h": None,
        "stations": [],
        "radius_km": RADIUS_KM,
        "aggregation": "参考点周边25km同一最新有效小时站点算术均值（自算，非官方全市均值）",
    }
    if rows is None:
        return result
    if not isinstance(rows, list):
        raise TypeError("实测数据必须是站点数组")
    candidates = []
    for row in rows:
        if not is_hangzhou(row):
            continue
        pm25 = number(row.get("PM2_5"))
        lat, lon = number(row.get("Latitude")), number(row.get("Longitude"))
        match = re.fullmatch(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})时",
            str(row.get("TimePointStr", "")).strip(),
        )
        if (
            pm25 is None
            or lat is None
            or lon is None
            or not match
            or not row.get("StationCode")
        ):
            continue
        if not (0 <= lat <= 90 and 0 <= lon <= 180):
            continue
        try:
            observed = datetime(*map(int, match.groups()), tzinfo=SHANGHAI)
        except ValueError:
            continue
        distance = distance_km(lat, lon)
        if observed <= now and distance <= RADIUS_KM:
            candidates.append(
                (
                    observed,
                    {
                        "code": str(row["StationCode"]),
                        "name": str(row.get("PositionName", row["StationCode"])),
                        "pm25": pm25,
                        "pm25_24h": number(row.get("PM2_5_24h")),
                        "latitude": lat,
                        "longitude": lon,
                        "distance_km": round(distance, 2),
                    },
                )
            )
    if not candidates:
        return result
    latest = max(t for t, _ in candidates)
    stations = {s["code"]: s for t, s in candidates if t == latest}
    with_24h = [s["pm25_24h"] for s in stations.values() if s["pm25_24h"] is not None]
    result.update(
        status="available" if now - latest <= timedelta(hours=3) else "stale",
        observed_at=latest.isoformat(),
        stations=sorted(stations.values(), key=lambda s: s["distance_km"]),
        mean_pm25=round(sum(s["pm25"] for s in stations.values()) / len(stations), 2),
        mean_pm25_24h=round(sum(with_24h) / len(with_24h), 2) if with_24h else None,
    )
    return result


def hourly_rows(payload, kind):
    """Validate provider time/unit contracts once, shared by all report consumers."""
    if not isinstance(payload, dict) or payload.get("timezone") != "Asia/Shanghai":
        raise ValueError("供应方时区缺失或不是 Asia/Shanghai")
    hourly, units = payload.get("hourly"), payload.get("hourly_units", {})
    if not isinstance(hourly, dict) or not isinstance(units, dict):
        raise TypeError("供应方缺少 hourly/hourly_units 对象")
    times = hourly.get("time")
    if not isinstance(times, list):
        raise TypeError("供应方缺少逐小时时间数组")
    expected = {"pm2_5": "μg/m³"} if kind == "air" else WEATHER_UNITS
    if kind == "air" and "pm2_5" not in hourly:
        raise ValueError("缺少 PM2.5 浓度数组")
    for key, unit in expected.items():
        if key not in hourly:
            continue
        if not isinstance(hourly[key], list) or len(hourly[key]) != len(times):
            raise ValueError(f"{key} 的时间和值数组长度不一致")
        if str(units.get(key, "")).replace("µ", "μ") != unit:
            raise ValueError(f"{key} 单位不符，应为 {unit}")
    result = {}
    for index, text in enumerate(times):
        t = datetime.fromisoformat(text)
        t = t.replace(tzinfo=SHANGHAI) if t.tzinfo is None else t.astimezone(SHANGHAI)
        if t.minute or t.second or t.microsecond or t in result:
            raise ValueError("小时数组包含非整点或重复时间")
        row = {}
        for key in expected:
            value = (
                number(
                    hourly[key][index], minimum=None if key == "temperature_2m" else 0
                )
                if key in hourly
                else None
            )
            if value is not None and (
                (key == "relative_humidity_2m" and value > 100)
                or (key == "wind_direction_10m" and value > 360)
            ):
                value = None
            row[key] = value
        result[t] = row
    return result


def fetch_json(url, post=False, timeout=20):
    headers = {"User-Agent": "Hangzhou-PM25/1.0 (personal air quality report)"}
    if post:
        headers["Referer"] = "https://air.cnemc.cn:18007/"
    for attempt in range(2):
        try:
            request = Request(url, data=b"" if post else None, headers=headers)
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8-sig"))
        except HTTPError as exc:
            if attempt or (exc.code != 429 and exc.code < 500):
                raise
        except (URLError, TimeoutError, OSError, HTTPException):
            if attempt:
                raise
        time.sleep(0.5)


def fetch_snapshot(days=5):
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": "Asia/Shanghai",
        "forecast_days": days,
    }
    urls = {
        "air": AIR_URL
        + "?"
        + urlencode(dict(params, hourly="pm2_5", domains="cams_global")),
        "weather": WEATHER_URL
        + "?"
        + urlencode(dict(params, hourly=",".join(WEATHER_UNITS), wind_speed_unit="ms")),
        "observations": CNEMC_URL,
    }
    snapshot = {
        "fetched_at": None,
        "air": None,
        "weather": None,
        "observations": None,
        "errors": {},
    }
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(fetch_json, url, key == "observations"): key
            for key, url in urls.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                value = future.result()
                if key == "observations":
                    if not isinstance(value, list):
                        raise ValueError("实测接口未返回站点数组")
                    value = [row for row in value if is_hangzhou(row)]
                snapshot[key] = value
            except (URLError, OSError, ValueError, TypeError, HTTPException) as exc:
                snapshot["errors"][key] = f"{type(exc).__name__}: {exc}"
    snapshot["fetched_at"] = datetime.now(SHANGHAI).isoformat(timespec="seconds")
    return snapshot
