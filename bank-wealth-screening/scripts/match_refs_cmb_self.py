"""招银自营新发份额的同系列老份额参照。

关键：招银每期新发都是**新登记编码**（regCode 逐期不同），所以按 regCode 匹配无效。
必须按**产品线名**（添金/添鑫/添利/丰和/鑫鼎/安悦/明裕/增瑞/增泰...）匹配，
并优先取**持有期相同**的老份额，其次取持有期最接近的。

用法: python3 match_refs_cmb_self.py --cand /tmp/cmb_full_refs6.json --out /tmp/cmb_full_refs7.json
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nav_stats as ns  # noqa: E402

NAV = os.path.join(HERE, "data", "nav_history")

# 招银自营产品线（系列名 -> 官方系列名近似）
LINES = ["添金", "添鑫", "添利", "丰和", "鑫鼎", "安悦", "明裕", "明睿",
         "增瑞", "增泰", "添元", "智远", "恒睿", "添福"]
# 策略族：同系列但不同策略的不能互相当参照
# （如 添金(人民币固收) vs 天添金(美元) ；增泰日开(固收) vs 全球商品融合/湾区全球优选(商品/全球)）
FOREIGN = re.compile(r"美元|欧元|港币|英镑|日元|离岸|跨境")
GLOBAL = re.compile(r"全球|国际|湾区|环球|世界|海外|商品|原油|黄金|外汇|QDII")


def strategy_of(name):
    """粗分策略族：人民币固收 / 外币 / 全球商品"""
    n = name or ""
    if FOREIGN.search(n):
        return "外币"
    if GLOBAL.search(n):
        return "全球"
    return "人民币"


def load_pts(code):
    p = os.path.join(NAV, f"{code}.csv")
    if not os.path.exists(p):
        return None
    rr = list(csv.DictReader(open(p, encoding="utf8")))
    if len(rr) < 2:
        return None
    return [(datetime.date.fromisoformat(r["date"]), float(r["nav"])) for r in rr]


def calc(code):
    pts = load_pts(code)
    if not pts:
        return None
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
    return dict(code=code, span=span, ann=ann, t6=ns.trailing(pts, 6), mdd=mdd,
                sharpe=sp, start=str(pts[0][0]), end=str(pts[-1][0]), n=len(pts))


def line_of(name):
    for L in LINES:
        if L in (name or ""):
            return L
    return None


def hold_days(name):
    m = re.search(r"(\d+)天", name or "")
    return int(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs6.json")
    ap.add_argument("--catalog", default="/tmp/cmb_catalog.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs7.json")
    ap.add_argument("--min-days", type=int, default=180)
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))
    catalog = {p["prdCode"]: p for p in json.load(open(a.catalog, encoding="utf8"))}

    # 参照池：招银自营代码(纯数字码) 且 span>=min_days
    pool = {}
    for f in os.listdir(NAV):
        if not f.endswith(".csv"):
            continue
        code = f[:-4]
        if not re.fullmatch(r"[0-9]{4,6}[A-Z]?", code):
            continue
        st = calc(code)
        if st and st["span"] >= a.min_days:
            nm = (catalog.get(code, {}) or {}).get("prdBrief") or ""
            st["name"] = nm
            st["line"] = line_of(nm)
            st["hold"] = hold_days(nm)
            st["strategy"] = strategy_of(nm)
            if st["line"]:
                pool[code] = st
    print(f"招银自营参照池(span>={a.min_days}d): {len(pool)}")
    by_line = {}
    for code, st in pool.items():
        by_line.setdefault(st["line"], []).append(code)
    for L, lst in by_line.items():
        print(f"  {L}: {len(lst)} 支")

    added = 0
    for r in rows:
        if r.get("ref") or (r.get("own") and r["own"]["span"] >= 180):
            continue
        if r["mgr"] != "招银理财":
            continue
        L = line_of(r["name"])
        if not L:
            continue
        # 策略族必须一致：人民币固收 不能用 外币/全球商品 当参照
        want = strategy_of(r["name"])
        cands = [c for c in by_line.get(L, []) if pool[c]["strategy"] == want]
        if not cands:
            continue
        hd = r["hold"]
        # 优先持有期相同，其次最接近；同条件下取成立最久
        cands = sorted(cands,
                       key=lambda c: (abs(pool[c]["hold"] - hd), -pool[c]["span"]))
        rc = cands[0]
        r["ref"] = dict(pool[rc], how="招银自营同产品线")
        added += 1
    print(f"  新增自营参照: {added}")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    n_ref = sum(1 for r in rows if r.get("ref"))
    n_own = sum(1 for r in rows if r.get("own") and r["own"]["span"] >= 180)
    n_cash = sum(1 for r in rows if r.get("cash_metrics") or r.get("seven_day"))
    covered = sum(1 for r in rows
                  if (r.get("own") and r["own"]["span"] >= 180) or r.get("ref")
                  or r.get("cash_metrics") or r.get("seven_day"))
    print(f"候选 {len(rows)} | 自身满期 {n_own} | 参照 {n_ref} | 七日年化 {n_cash}")
    print(f"有口径覆盖: {covered}/{len(rows)} ({covered/len(rows):.1%})")


if __name__ == "__main__":
    main()
