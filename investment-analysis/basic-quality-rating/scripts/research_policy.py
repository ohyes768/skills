"""Bounded source routing decisions; no network calls, credentials or sleeping."""

import math
import re

KINDS = frozenset(
    ("quota", "auth", "blocked", "rate_limit", "timeout", "network", "not_found", "unknown")
)


def new_routes(names):
    if (
        not isinstance(names, list)
        or not 1 <= len(names) <= 4
        or any(
            not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name)
            for name in names
        )
        or len(set(names)) != len(names)
    ):
        raise ValueError("配置 1–4 个不重复的渠道 ID（英文、数字、下划线或连字符）")
    return {
        name: {"disabled": False, "failures": 0, "ready_at": 0, "reason": None} for name in names
    }


def classify_failure(error):
    if isinstance(error, str):
        error = {"message": error}
    if not isinstance(error, dict):
        raise TypeError("error 必须为错误对象或错误文本，不能传网页正文")
    status = error.get("http_status")
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        raise ValueError("http_status 必须是 HTTP 整数状态码")
    message = str(error.get("message", ""))[:2000].lower()
    if status == 402 or any(
        word in message
        for word in (
            "insufficient credits",
            "payment required",
            "quota exceeded",
            "余额不足",
            "额度不足",
        )
    ):
        kind = "quota"
    elif status == 401 or any(
        word in message for word in ("invalid api key", "unauthorized", "authentication failed")
    ):
        kind = "auth"
    elif status == 429:
        kind = "rate_limit"
    elif status == 403:
        kind = "blocked"
    elif status in (404, 410):
        kind = "not_found"
    elif "timeout" in message or "timed out" in message or "超时" in message:
        kind = "timeout"
    elif (status is not None and status >= 500) or any(
        word in message for word in ("network", "connection", "unreachable", "dns")
    ):
        kind = "network"
    else:
        kind = error.get("kind", "unknown")
        if kind not in KINDS:
            kind = "unknown"
    delay = error.get("retry_after", 5)
    if (
        type(delay) not in (int, float)
        or (type(delay) is float and not math.isfinite(delay))
        or delay < 0
    ):
        delay = 5
    return {"kind": kind, "retry_after": min(delay, 300)}


def fail_route(route, error, *, now):
    failure = classify_failure(error)
    kind = failure["kind"]
    if route["disabled"]:
        # Late outcomes must not erase a permanent block or grow its counter.
        return failure
    route["reason"] = kind
    if kind == "not_found":
        return failure
    # Several dimensions can hold outstanding receipts for the same route.
    route["failures"] = min(2, route["failures"] + 1)
    if kind in ("quota", "auth", "blocked", "unknown") or route["failures"] >= 2:
        route["disabled"] = True
    else:
        route["ready_at"] = now + max(1, failure["retry_after"])
    return failure


def select_route(routes, attempts, *, now):
    candidates = []
    for name, route in routes.items():
        used = [a for a in attempts if a["provider"] == name]
        if (
            route["disabled"]
            or len(used) >= 2
            or any(a["outcome"] in ("empty", "not_found") for a in used)
        ):
            continue
        candidates.append((len(used), name, route))
    ready = [item for item in candidates if item[2]["ready_at"] <= now]
    if ready:
        # Prefer an unused alternate route over repeating a failed request.
        _, name, _ = min(ready, key=lambda item: item[0])
        return {"action": "search", "provider": name}
    if candidates:
        return {"action": "wait", "retry_at": min(item[2]["ready_at"] for item in candidates)}
    if all(route["disabled"] for route in routes.values()):
        return {"action": "stop", "reason": "所有配置渠道均不可用；停止取证并披露缺口"}
    return {"action": "decide", "reason": "本轮渠道已用尽；复用已有证据或按剩余轮次补证"}
