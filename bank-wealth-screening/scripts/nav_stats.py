"""理财产品指标一览表。

用法:
    python nav_stats.py <code> [<code> ...] [--no-refresh]

按 code 拉取(默认)/读取历史净值，输出: 成立时长、近6月年化、成立以来年化、
历史最大回撤、成立Sharpe、近1年Sharpe。无风险利率按 1.5%。

"""
import argparse
import csv
import datetime
import glob
import json
import math
import os
import re
import subprocess
import sys

from code_convert import convert

import numpy as np

RF = 0.015
HERE = os.path.dirname(os.path.abspath(__file__))
NAV_DIR = os.path.join(HERE, "data", "nav_history")
# 各管理人结构化净值缓存目录（可用环境变量 BWS_NAV_DIR 覆盖；历史研究缓存 ~/study/nav 已删除，需重新抓取）
JSON_SOURCES = [
    ("citic", ["navDate", "nav"]),            # {'navDate':'20261124','nav':'1.02'}
    ("ny",    ["date", "netValue"]),          # {'date':'2026-11-24','netValue':'1.11'}
    ("hx",    ["netValueDate", "shareNetVal"]),  # 净值报告 rows
    ("xy",    ["dataDt", "adjustedValue"]),   # 复权净值，回退 effTotNetVal
    ("ms",    None), ("ceb", None), ("boc", None),  # 无结构化历史，仅占位
]
STUDY_NAV = os.environ.get("BWS_NAV_DIR", os.path.expanduser("~/study/nav"))


NAME_HINT = {}  # code -> 产品名（从 JSON 缓存顺带取到）


def _load_json(code):
    """从 <缓存目录>/<mgmt>/<code>*.json 读历史净值，返回 [(date, nav)] 或 None。"""
    for mgmt, fields in JSON_SOURCES:
        if not fields:
            continue
        for f in sorted(glob.glob(os.path.join(STUDY_NAV, mgmt, f"{code}*"))):
            try:
                d = json.load(open(f))
            except Exception:
                continue
            rows = d.get("rows") if isinstance(d, dict) else d
            if not rows:
                continue
            name = (d.get("name") or d.get("productName") or d.get("title") or "")
            if name:
                NAME_HINT[code] = re.sub(r"[\[【].*?[\]】]", "", name)[:40]
            pts = []
            for r in rows:
                dt, nv = str(r.get(fields[0]) or ""), r.get(fields[1])
                if fields[1] == "adjustedValue" and not nv:
                    nv = r.get("effTotNetVal")
                if not dt or nv in (None, "", 0):
                    continue
                dt = dt[:10].replace(".", "-")
                try:
                    pts.append((datetime.date.fromisoformat(dt), float(nv)))
                except ValueError:
                    continue
            if len(pts) >= 2:
                return sorted(set(pts))
    return None


def load(code):
    path = os.path.join(NAV_DIR, f"{code.upper()}.csv")
    if not os.path.exists(path):
        pts = _load_json(code.upper())
        if pts:
            return pts
        raise FileNotFoundError(code)
    rows = list(csv.DictReader(open(path)))
    return [(datetime.date.fromisoformat(r["date"]), float(r["nav"])) for r in rows]


def ann_return(pts, span_days=None):
    v0, v1 = pts[0][1], pts[-1][1]
    span = span_days or (pts[-1][0] - pts[0][0]).days
    return (v1 / v0) ** (365 / span) - 1 if span > 0 else None


def trailing(pts, months):
    start = pts[-1][0] - datetime.timedelta(days=30 * months)
    prior = [x for x in pts if x[0] <= start]
    if len(prior) < 2:
        return None
    span = (pts[-1][0] - prior[-1][0]).days
    return (pts[-1][1] / prior[-1][1]) ** (365 / span) - 1 if span > 0 else None


def stats(pts):
    """-> (年化, 年化波动, sharpe, 最大回撤)"""
    v = np.array([x[1] for x in pts])
    d = [x[0] for x in pts]
    ann = ann_return(pts)
    ret = v[1:] / v[:-1] - 1
    step = np.median([(b[0] - a[0]).days for a, b in zip(pts, pts[1:])])
    vol = ret.std(ddof=1) * math.sqrt(365 / step)
    sharpe = (ann - RF) / vol if vol > 0 else None
    mdd = ((v / np.maximum.accumulate(v)) - 1).min()
    return ann, vol, sharpe, mdd


def since(pts, days, min_points=50):
    sub = [x for x in pts if x[0] >= pts[-1][0] - datetime.timedelta(days=days)]
    return sub if len(sub) >= min_points else None


def fmt(x, pct=True):
    if x is None:
        return "--"
    return f"{x:+.2%}" if pct else f"{x:+.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--no-refresh", action="store_true",
                    help="跳过拉取，直接用本地缓存的历史净值")
    a = ap.parse_args()
    if not a.no_refresh:
        os.makedirs(NAV_DIR, exist_ok=True)
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_nav_history.py"),
                        "--out", NAV_DIR, *a.codes], check=False)
    print(f"{'产品':<26}{'代码':<14}{'风险':>4}{'成立时长':>9}{'近6月年化':>10}{'成立年化':>10}"
          f"{'最大回撤':>10}{'成立Sharpe':>12}{'近1年Sharpe':>13}")
    for code in a.codes:
        code = code.upper()
        try:
            pts = load(code)
        except FileNotFoundError:
            print(f"{'?':<26}{code:<14}{'':>4} 无历史净值且拉取失败，检查网络后重试")
            continue
        if not pts:
            print(f"{'?':<26}{code:<14}{'':>4} 净值接口无数据（可能未披露/不支持该代码）")
            continue
        try:
            info = convert(code)
            name = info.name or code
            risk = info.extra.get("risk") or ""
            m = re.search(r"(PR?\d)", risk)
            risk = m.group(1) if m else risk[:6]
        except Exception:
            name, risk = NAME_HINT.get(code, code), ""
            if name == code:
                risk = ""
        name = name if len(name) <= 24 else name[:23] + "…"
        span = (pts[-1][0] - pts[0][0]).days
        dur = f"{span//365}年{span%365}天" if span >= 365 else f"{span}天"
        ann, _, sp, mdd = stats(pts)
        t6 = trailing(pts, 6)
        y = since(pts, 365)
        sp1y = stats(y)[2] if y else None
        print(f"{name:<26}{code:<14}{risk:>4}{dur:>9}{fmt(t6):>10}{fmt(ann):>10}{fmt(mdd):>10}"
              f"{fmt(sp, pct=False):>12}{fmt(sp1y, pct=False):>13}")


if __name__ == "__main__":
    main()
