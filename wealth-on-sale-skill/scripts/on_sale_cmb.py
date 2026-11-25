#!/usr/bin/env python3
"""招银自营可申购产品清单（不含代销）

用法:
  python on_sale_cmb.py                 # 常开/持有期可申购 + 今日在募集期
  python on_sale_cmb.py --risk R2       # 按风险过滤: R2 或 R2,R3
  python on_sale_cmb.py --manager 招银  # 按名称关键字过滤

数据源: m.cmbchina.com /api/financing/product-list（目录约770支，2026-11起仅招银自营，代销已不在返回中）
自营判定: 招银自营产品 prdCode 为 4-6 位数字（可带份额字母，如 120053A、8914）；
      代销产品代码带机构前缀（XY/GD/MS/JX/GY/JY 等），已默认排除。
      代销渠道研究代码在 ~/study/wealth-distribution-channel/。
判定: 长期开放型（日开/天天/最短持有期/定开且未到期）视为可申购；
      封闭式新发按募集窗口 beginDate~endDate 是否覆盖今天。
"""
import argparse, datetime, json, re, sys
import requests

from term_parse import term_days, hold_days

API = "https://m.cmbchina.com/api/financing/product-list"
RISK = {"R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4", "R5": "R5",
        "低风险": "R1", "中低风险": "R2", "中风险": "R3",
        "中高风险": "R4", "高风险": "R5"}
OPEN_PAT = re.compile(r"日开|天天|活期|最短持有|最低持有|天持有|月持有|持有期|定开")
RETAIL_EXCL = re.compile(r"机构专享|私行|私享|私募|尊享")


def pdate(s):
    return datetime.date.fromisoformat(s.split(" ")[0]) if s else None


def fetch_all():
    out, page = [], 1
    while True:
        body = None
        for i in range(4):  # 翻页中途会限频，重试并退避
            try:
                r = requests.get(API, params={"pageIndex": page, "pageSize": 100},
                                 timeout=30, headers={"User-Agent": "Mozilla/5.0"})
                body = r.json().get("body")
                if body and body.get("data"):
                    break
            except Exception:
                pass
            import time
            time.sleep(5 * (i + 1))
        if not (body and body.get("data")):
            print(f"第{page}页拉取失败（限频?），已取 {len(out)} 条", file=sys.stderr)
            break
        out += body["data"]
        total = body.get("total") or 0
        if page * 100 >= total or not body["data"]:
            break
        page += 1
        import time
        time.sleep(1)  # 翻页限频保护
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--risk", default=None, help="如 R2 或 R2,R3")
    ap.add_argument("--manager", default=None, help="名称关键字，如 招银")
    ap.add_argument("--retail", action="store_true",
                    help="只看个人可买：排除大额存单(≥20万)、机构专享、私行/私享、私募")
    ap.add_argument("--max-amt", type=float, default=None, metavar="元",
                    help="起购金额上限，如 --max-amt 200000 排除 20 万起投产品")
    ap.add_argument("--min-days", type=int, default=None,
                    help="期限最短天数下限（按期限字段解析，含「365天以上」这类开放区间）")
    a = ap.parse_args()
    risks = {x.strip().upper() for x in a.risk.split(",")} if a.risk else None
    today = datetime.date.today()
    prods = fetch_all()
    picked = []
    for p in prods:
        exp = pdate(p.get("expireDate")) or today
        if exp < today:
            continue  # 已到期
        beg, end = pdate(p.get("beginDate")), pdate(p.get("endDate"))
        term = p.get("term") or ""
        name = p.get("prdName") or ""
        m = re.search(r"R\d", p.get("risk") or "")
        raw_risk = p.get("risk") or ""
        risk = m.group(0) if m else RISK.get(raw_risk.split("(")[0].strip(), raw_risk.split("(")[0].strip() or "?")
        if risks and risk not in risks:
            continue
        if not re.fullmatch(r"[0-9]{4,6}[A-Z]?", p["prdCode"]):
            continue  # 只看招银自营，代销（XY/GD/MS/JX/GY/JY 等前缀）排除
        if a.manager and a.manager not in name:
            continue
        if a.retail and RETAIL_EXCL.search(name + (p.get("prdBrief") or "")):
            continue
        if a.retail and re.match(r"^(PB|PW|GDPB|GDPW|GYPB|GYPW|JXPB|JXPW|MSPB|MSPW|HXPW|PAPW)", p["prdCode"]):
            continue  # 私行/私募款代码
        if a.retail and (p.get("initMoney") or 0) >= 200000:
            continue  # 大额存单等高门槛产品
        init = p.get("initMoney") or 0
        if a.max_amt is not None and init > a.max_amt:
            continue  # 起购超上限；initMoney=0 表示接口未披露（普通理财多为1元/100元起）
        if a.min_days is not None:
            hd = hold_days(name, term)
            if hd is None or hd < a.min_days:
                continue
        window_open = bool(beg and end and beg <= today <= end
                           and beg.year >= today.year - 1)  # 老产品残留窗口不算
        always_open = bool(OPEN_PAT.search(name) or OPEN_PAT.search(term))
        if not (window_open or always_open):
            continue
        picked.append((p, risk, term, window_open))
    # 非窗口（常开）产品只保留近2年新发的
    picked = [(p, r, t, w) for p, r, t, w in picked
              if w or (pdate(p.get("beginDate")) or today).year >= today.year - 2]
    print(f"=== 招银自营可申购（今天 {today}）共 {len(picked)} 支 ===\n")
    for p, risk, term, w in sorted(picked, key=lambda x: (x[1], x[0].get("prdCode"))):
        tag = "募集期" if w else "常开"
        beg = (p.get("beginDate") or "")[:10] or "?"
        print(f"[{risk}] {tag} {p['prdCode']:<9} 发售{beg} {term:<10} {p.get('prdBrief') or p.get('prdName')}")


if __name__ == "__main__":
    main()
