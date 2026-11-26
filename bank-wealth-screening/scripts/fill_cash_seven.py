"""给万份收益型候选(净值恒1.0)补七日年化业绩口径。

用法: python3 fill_cash_seven.py --cand /tmp/cmb_full_refs.json --out /tmp/cmb_full_refs2.json
"""
import argparse
import csv
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cash_wanli_fetch as C  # noqa: E402

NAV = os.path.join(HERE, "data", "nav_history")
MS_NAV = os.path.join(HERE, "ms_nav")

# 各管理人现金类产品的官网检索关键字 -> 官网产品名系列
MS_KEYWORD = {
    "MS": "天天增利现金管理",
    "MS": "贵竹固收增利天天盈",
    "PA": None, "NB": None, "ZX": None, "GD": None, "JY": None,
}


def seven_day_stats(code):
    """从 ms_nav/<code>.json 取七日年化序列。"""
    p = os.path.join(MS_NAV, f"{code}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf8"))
    sds = []
    for r in d.get("rows") or []:
        v = r.get("seven_day")
        try:
            sds.append((r["date"], float(v)))
        except (TypeError, ValueError):
            continue
    if len(sds) < 30:
        return None
    last30 = [v for _, v in sds[-30:]]
    last90 = [v for _, v in sds[-90:]]
    return dict(latest=sds[-1][1], avg30=sum(last30) / len(last30),
                avg90=sum(last90) / len(last90), n=len(sds),
                start=sds[0][0], end=sds[-1][0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs2.json")
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))

    # 找出所有万份收益型候选
    flat = []
    for r in rows:
        p = os.path.join(NAV, f"{r['code']}.csv")
        if not os.path.exists(p):
            continue
        rr = list(csv.DictReader(open(p, encoding="utf8")))
        if len(rr) < 2:
            continue
        vals = [float(x["nav"]) for x in rr]
        if max(vals) - min(vals) < 1e-9:
            flat.append(r)
    print(f"万份收益型候选: {len(flat)} 只")

    # 按管理人分组，用产品名去民生/其他官网搜对应系列的七日年化
    # 优先用"同登记编码"的老份额（万份收益型产品的登记编码在招行目录里可见）
    catalog = {p["prdCode"]: p for p in json.load(open("/tmp/cmb_catalog.json", encoding="utf8"))}

    # 1) 先给已经在 ms_nav 缓存里的老份额建索引（按核心词）
    ms_index = {}
    for f in os.listdir(MS_NAV):
        if not f.endswith(".json"):
            continue
        d = json.load(open(os.path.join(MS_NAV, f), encoding="utf8"))
        nm = d.get("name") or ""
        if nm:
            ms_index.setdefault(nm, os.path.join(MS_NAV, f))

    filled = 0
    for r in flat:
        p = catalog.get(r["code"], {})
        reg = p.get("regCode")
        # 找同登记编码的、已缓存七日年化的份额
        best = None
        for code, pp in catalog.items():
            if code == r["code"]:
                continue
            if pp.get("regCode") != reg:
                continue
            s = seven_day_stats(code)
            if s:
                best = (code, s)
                break
        if best:
            r["seven_day"] = best[1]
            r["seven_day_ref"] = best[0]
            filled += 1
    print(f"按同登记编码匹配到七日年化: {filled} 只")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"写入 {a.out}")


if __name__ == "__main__":
    main()
