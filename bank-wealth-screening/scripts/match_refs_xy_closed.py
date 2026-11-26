"""兴银封闭式系列的跨期号参照匹配。

兴银官网 productName 带期号("稳利安盈封闭式2023年231期")，招行货架带的是
当期期号("稳利安盈封闭式2026年665期")，按期号匹配必然落空。
但同一**产品线**的早期次往往有很长历史（封闭式披露净值滞后，需要找老期次）。

规则: 按"产品线主干"(去期号/年/期) 归组，组内取净值历史最深的份额做参照。
用法: python3 match_refs_xy_closed.py --cand /tmp/cmb_full_refs8.json --out /tmp/cmb_full_refs9.json
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nav_stats as ns  # noqa: E402

XY = os.path.join(HERE, "xy")


def xy_stats(code):
    f = os.path.join(XY, f"{code}.json")
    if not os.path.exists(f):
        return None
    try:
        d = json.load(open(f, encoding="utf8"))
    except Exception:
        return None
    rows = d.get("rows") or []
    pts = []
    for r in rows:
        dt = r.get("netvalDt") or r.get("dataDt")
        nv = r.get("adjustedValue")
        if not dt or nv is None:
            continue
        try:
            pts.append((datetime.date.fromisoformat(str(dt)[:10]), float(nv)))
        except Exception:
            pass
    if len(pts) < 2:
        return None
    pts.sort(key=lambda x: x[0])
    span = (pts[-1][0] - pts[0][0]).days
    if span <= 0:
        return None
    vals = [v for _, v in pts]
    if max(vals) - min(vals) < 1e-9:
        return None
    try:
        ann, _, sp, mdd = ns.stats(pts)
    except Exception:
        return None
    if ann is None:
        return None
    return dict(code=code, span=span, ann=float(ann), t6=ns.trailing(pts, 6),
                mdd=float(mdd), sharpe=float(sp), start=str(pts[0][0]),
                end=str(pts[-1][0]), n=len(pts),
                name=(d.get("productName") or "")[:52],
                how="官网同产品线(跨期号)")


def line_key(name):
    """去期号/年份/份额字母/通用后缀 -> 产品线主干"""
    s = re.sub(r"\d{4}年", "", name or "")
    s = re.sub(r"\d+期", "", s)
    s = re.sub(r"\d+号", "", s)
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"\s+", "", s)
    # 招行名尾部带份额字母(…封闭式F)，官网没有 —— 去掉尾部孤立大写字母
    s = re.sub(r"[A-Z]$", "", s)
    # 官网名带通用后缀(固收类理财产品/现金管理类理财产品)，招行名没有
    s = re.sub(r"(固收类|现金管理类|净值型|混合类|固收增强类)?理财产品$", "", s)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs8.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs9.json")
    ap.add_argument("--min-days", type=int, default=180)
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))

    # 兴银官网产品线 -> 最深份额
    lines = {}
    for f in glob.glob(os.path.join(XY, "*.json")):
        try:
            d = json.load(open(f, encoding="utf8"))
        except Exception:
            continue
        nm = d.get("productName") or ""
        if not nm:
            continue
        k = line_key(nm)
        if not k:
            continue
        rowsn = d.get("rows") or []
        cur = lines.get(k)
        if cur is None or len(rowsn) > cur[1]:
            lines[k] = (os.path.basename(f)[:-5], len(rowsn), nm)
    print(f"兴银产品线: {len(lines)} 组")

    added = 0
    for r in rows:
        if r.get("ref") or (r.get("own") and r["own"]["span"] >= 180):
            continue
        if r["mgr"] != "兴银":
            continue
        k = line_key(r["name"])
        hit = lines.get(k)
        if not hit:
            continue
        st = xy_stats(hit[0])
        if not st or st["span"] < a.min_days:
            continue
        r["ref"] = st
        added += 1
    print(f"  新增兴银参照: {added}")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    covered = sum(1 for r in rows
                  if (r.get("own") and r["own"]["span"] >= 180) or r.get("ref")
                  or r.get("cash_metrics") or r.get("seven_day"))
    print(f"候选 {len(rows)} | 有口径覆盖 {covered} ({covered/len(rows):.1%})")


if __name__ == "__main__":
    main()
