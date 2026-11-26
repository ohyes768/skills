"""给各管理人现金管理类(万份收益型)候选补业绩口径。

各家口径:
  信银 citic:  productInfo/search 返回 sevenDaysIncomeRate(七日年化) + totalYearIncomeRate(成立以来年化)
  兴银 xy:     performanceTrend 返回 adjustedValue，但货币型净值恒 1；改用 productInfo 的收益率字段
  中银/平安/宁银: 无直连七日年化接口 -> 标注"无业绩可参照"，改用招行 cfweb 的代销份额净值(若有)

用法: python3 fill_cash_all.py --cand /tmp/cmb_full_refs2.json --out /tmp/cmb_full_refs3.json
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_dist_nav as F  # noqa: E402

NAV = os.path.join(HERE, "data", "nav_history")


def is_flat(code):
    p = os.path.join(NAV, f"{code}.csv")
    if not os.path.exists(p):
        return False
    rr = list(csv.DictReader(open(p, encoding="utf8")))
    if len(rr) < 2:
        return False
    vals = [float(x["nav"]) for x in rr]
    return max(vals) - min(vals) < 1e-9


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs2.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs3.json")
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))
    flat = [r for r in rows if is_flat(r["code"])]
    print(f"万份收益型: {len(flat)}")

    # ---- 信银 ----
    zx = [r for r in flat if r["mgr"] == "信银"]
    print(f"\n== 信银 {len(zx)} 只")
    if zx:
        try:
            prods = F.citic_search("日盈象天天利")
            print(f"  官网检索到 {len(prods)} 支")
            # key = (期号, 份额尾字母)，只保留代销含"招商银行"的份额
            idx = {}
            for p in prods:
                nm = p.get("prodName") or ""
                m = re.search(r"天天利(\d+)号", nm)
                if not m:
                    continue
                code = p.get("prodCode") or ""
                tail = code[-1] if code else ""
                if "招商银行" not in (p.get("distributorNames") or ""):
                    continue
                idx[(m.group(1), tail)] = p
            hit = 0
            for r in zx:
                m = re.search(r"天天利(\d+)号([A-Z])$", r["name"])
                if not m:
                    continue
                p = idx.get((m.group(1), m.group(2)))
                if not p:
                    continue
                sd7 = num(p.get("sevenDaysIncomeRate"))
                tot = num(p.get("totalYearIncomeRate"))
                if not sd7:
                    continue
                r["cash_metrics"] = dict(seven_day=sd7, total_year=tot,
                                         ref=p.get("prodName"), ref_code=p.get("prodCode"),
                                         distributor=p.get("distributorNames"))
                hit += 1
            print(f"  按(期号+份额字母+招行代销)匹配: {hit}/{len(zx)}")
            for r in zx[:6]:
                cm = r.get("cash_metrics")
                if not cm:
                    continue
                tot = cm["total_year"]
                tot_s = "--" if tot is None else f"{tot:.4%}"
                print(f"    {r['code']:<10} {r['name'][:32]:<34} "
                      f"七日年化{cm['seven_day']:.4%} 成立以来{tot_s} "
                      f"[{cm['ref_code']}]")
        except Exception as e:
            print(f"  信银失败: {str(e)[:80]}")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"\n写入 {a.out}")


if __name__ == "__main__":
    main()
