"""全量候选业绩统计 + 同系列老份额参照。

用法: python3 stats_cmb_full.py --cand /tmp/cmb_full_cand.json --out /tmp/cmb_full_stats.json
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nav_stats as ns  # noqa: E402

NAV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nav_history")
XY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xy")
HX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx")


def load_pts(code):
    p = os.path.join(NAV, f"{code}.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf8")))
    if len(rows) < 2:
        return None
    return [(datetime.date.fromisoformat(r["date"]), float(r["nav"])) for r in rows]


def calc(code):
    pts = load_pts(code)
    if not pts:
        return None
    span = (pts[-1][0] - pts[0][0]).days
    vals = [v for _, v in pts]
    flat = max(vals) - min(vals) < 1e-9
    ann, _, sp, mdd = ns.stats(pts)
    return dict(span=span, ann=ann, t6=ns.trailing(pts, 6), mdd=mdd, sharpe=sp,
                flat=flat, start=str(pts[0][0]), end=str(pts[-1][0]), n=len(pts))


def series_key(name):
    """从产品名抽系列核心词（去期号/份额字母/持有期数字）。"""
    s = re.sub(r"[（(].*?[)）]", "", name or "")
    s = re.sub(r"第?\d+期.*$", "", s)
    s = re.sub(r"\d+号.*$", "", s)
    s = re.sub(r"\d+天.*$", "", s)
    s = re.sub(r"[A-Z]$", "", s)
    s = re.sub(r"(理财)?(产品|计划|理财)?$", "", s)
    return s.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_cand.json")
    ap.add_argument("--out", default="/tmp/cmb_full_stats.json")
    a = ap.parse_args()
    cand = json.load(open(a.cand, encoding="utf8"))

    # 候选自身的业绩
    out = []
    for c in cand:
        c["own"] = calc(c["code"])
        out.append(c)

    # 同系列老份额索引：按 series_key 聚合所有已缓存的 code
    index = {}
    for f in glob.glob(os.path.join(NAV, "*.csv")):
        code = os.path.basename(f)[:-4]
        st = calc(code)
        if st and st["span"] >= 180 and not st["flat"]:
            index.setdefault(code, st)

    print(f"候选 {len(out)}，其中自身有净值 {sum(1 for c in out if c['own'])}")
    print(f"可用参照池（span>=180d, 非万份收益型）: {len(index)}")
    json.dump(out, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"写入 {a.out}")


if __name__ == "__main__":
    main()
