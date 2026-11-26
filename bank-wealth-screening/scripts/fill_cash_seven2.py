"""给万份收益型候选补七日年化：按产品名系列核心词去民生官网找同系列老份额。

用法: python3 fill_cash_seven2.py --cand /tmp/cmb_full_refs.json --out /tmp/cmb_full_refs2.json
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cash_wanli_fetch as C  # noqa: E402

NAV = os.path.join(HERE, "data", "nav_history")
MS_NAV = os.path.join(HERE, "ms_nav")


def seven_day_stats(code):
    p = os.path.join(MS_NAV, f"{code}.json")
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf8"))
    sds = []
    for r in d.get("rows") or []:
        try:
            sds.append((r["date"], float(r["seven_day"])))
        except (TypeError, ValueError):
            continue
    if len(sds) < 30:
        return None
    last30 = [v for _, v in sds[-30:]]
    last90 = [v for _, v in sds[-90:]]
    return dict(latest=sds[-1][1], avg30=sum(last30) / len(last30),
                avg90=sum(last90) / len(last90), n=len(sds),
                start=sds[0][0], end=sds[-1][0])


def core(name):
    """产品名 -> 民生官网可检索的系列名。"""
    s = re.sub(r"[（(].*?[)）]", "", name or "")
    s = re.sub(r"\d+号", "", s)
    s = re.sub(r"\d+期", "", s)
    s = re.sub(r"[A-Z]$", "", s)
    s = s.replace("理财产品", "").replace("理财", "")
    s = re.sub(r"^民生", "", s)          # 官网检索不带"民生"前缀
    s = re.sub(r"\d+天持有期", "", s)     # 去掉持有期数字，官网名是"贵竹月月盈"这类
    s = re.sub(r"^\d+天", "", s)
    return s.strip()


def is_flat(code):
    p = os.path.join(NAV, f"{code}.csv")
    if not os.path.exists(p):
        return False
    rr = list(csv.DictReader(open(p, encoding="utf8")))
    if len(rr) < 2:
        return False
    vals = [float(x["nav"]) for x in rr]
    return max(vals) - min(vals) < 1e-9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs2.json")
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))

    flat = [r for r in rows if is_flat(r["code"])]
    print(f"万份收益型: {len(flat)} 只")

    # 民生系（MS）才用民生七日年化；其他管理人的现金类另想办法
    ms_rows = [r for r in flat if r["mgr"] == "民生"]
    print(f"  其中民生系: {len(ms_rows)}")

    # 按核心词聚合
    groups = {}
    for r in ms_rows:
        groups.setdefault(core(r["name"]), []).append(r)
    print(f"  核心词分组: {len(groups)}")

    filled = 0
    for kw, lst in groups.items():
        try:
            prods = C.search_products(kw)
        except Exception as e:
            print(f"  {kw}: 搜索失败 {str(e)[:50]}")
            continue
        # 取成立最早且有七日年化数据的
        best = None
        cands = []
        for p in prods:
            ed = p.get("ESTAB_DATE")
            code = p.get("REAL_PRD_CODE")
            if not ed or not code:
                continue
            try:
                ed_i = int(str(ed))
            except ValueError:
                continue
            if ed_i > 20260101:
                continue
            cands.append((ed_i, code, p.get("PRD_NAME") or ""))
        cands.sort()
        for ed_i, code, nm in cands[:8]:
            s = seven_day_stats(code)
            if s:
                if best is None or ed_i < best[0]:
                    best = (ed_i, code, nm, s)
                break
        if best:
            for r in lst:
                r["seven_day"] = best[3]
                r["seven_day_ref"] = f"{best[1]} {best[2][:30]}"
            filled += len(lst)
            print(f"  {kw[:26]:<28} -> {best[1]} (成立{best[0]}) "
                  f"最新七日年化{best[3]['latest']:.4%} 均90日{best[3]['avg90']:.4%} "
                  f"[{best[3]['start']}~{best[3]['end']}] x{len(lst)}")
        else:
            print(f"  {kw[:26]:<28} -> 无七日年化参照")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"\n已补七日年化: {filled} 只，写入 {a.out}")


if __name__ == "__main__":
    main()
