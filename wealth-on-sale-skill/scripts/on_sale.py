#!/usr/bin/env python3
"""杭银理财在售产品查询：当前买入窗口开放的产品，按系列归并

用法:
  python on_sale.py            # 今天窗口开放的（默认）
  python on_sale.py --all      # 全部“在售”状态产品
  python on_sale.py --risk R2  # 按风险过滤: R1/R2/R3/R4/R5（可逗号分隔多个）

数据源: 杭银理财官网静态 JSON（全量 5552 个产品，含在售/存续/到期）
"""
import argparse, json, re, sys
from datetime import date, datetime

import requests, urllib3

urllib3.disable_warnings()

URL = "https://www.hzbankwealth.cn/eportal/hzbw/product_data.json"
RISK_MAP = {"低风险": "R1", "中低风险": "R2", "中风险": "R3",
            "中高风险": "R4", "高风险": "R5"}


def load_products():
    r = requests.get(URL, timeout=20, verify=False, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.json().get("product", [])


def pdate(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="列出全部在售状态产品（不按窗口过滤）")
    ap.add_argument("--risk", default=None, help="只看指定风险等级，如 R2 或 R1,R2")
    args = ap.parse_args()
    risks = {r.strip().upper() for r in args.risk.split(",")} if args.risk else None
    today = date.today()

    prods = load_products()
    picked = []
    for p in prods:
        if p.get("chanpinzhuangtai") != "在售":
            continue
        risk = RISK_MAP.get(p.get("rizengzhang"), "?")
        if risks and risk not in risks:
            continue
        s, e = pdate(p.get("order_fund_date") or ""), pdate(p.get("order_end_date") or "")
        if not args.all and not ((s or today) <= today <= (e or today)):
            continue
        picked.append((p, risk, s, e))

    # 按系列归并（去掉份额后缀和括号内容）
    groups = {}
    for p, risk, s, e in picked:
        key = re.sub(r"理财[A-Z]{1,2}款.*$", "", re.sub(r"（.*$", "", p.get("contenttitle") or "")).strip()
        g = groups.setdefault(key, {"risk": risk, "mode": p.get("yunzuomoshi"),
                                    "term": p.get("licaiqixian") or "每日开放",
                                    "bench": p.get("nianzengzhang"), "n": 0, "windows": set()})
        g["n"] += 1
        g["windows"].add((s, e))

    open_now = {id(g) for g in groups.values()
                if any((s or today) <= today <= (e or today) for s, e in g["windows"])}
    print(f"=== 在售开放窗口产品（今天 {today}）共 {len(picked)} 个份额 / {len(groups)} 个系列 ===\n")
    for k, g in sorted(groups.items(), key=lambda kv: min(kv[1]["windows"]) or (None, None)):
        ws = "; ".join(f"{s or '常开'}~{e or '常开'}" for s, e in sorted(g["windows"]))
        flag = "←窗口开放" if any((s or today) <= today <= (e or today) for s, e in g["windows"]) else "  窗口已过"
        print(f"[{g['risk']}] {g['mode']} {k}")
        print(f"    期限: {g['term']}   基准: {g['bench']}   份额数: {g['n']}")
        print(f"    窗口: {ws}  {flag}\n")


if __name__ == "__main__":
    main()
