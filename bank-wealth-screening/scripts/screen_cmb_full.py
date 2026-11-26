"""用完整目录(7689只)重筛: R1/R2 + 持有期<=180天 + 排除大额存单/私行/机构专享。

用法: python3 screen_cmb_full.py --catalog /tmp/cmb_catalog.json --out /tmp/cmb_full_cand.json
"""
import argparse
import datetime
import json
import re
import sys

sys.path.insert(0, "/home/ohyes768/skills/bank-wealth-screening/scripts")
from term_parse import hold_days  # noqa: E402

RISK = {"R1": "R1", "R2": "R2", "R3": "R3", "R4": "R4", "R5": "R5",
        "低风险": "R1", "中低风险": "R2", "中风险": "R3", "中高风险": "R4", "高风险": "R5"}
# 私行/私募份额：代码的字母前缀里含独立的 PB / PW 段
# （与普通 A/C/D 份额共享同一登记编码，但仅私行/私募渠道可买）。
# 例：120084A(零售) vs PB120084(私行尊享)，JYPB0123 = JY + PB + 0123。
PRIVATE_SEG = re.compile(r"PB|PW")
# 定向/机构专属份额：NBD/JXD/BYD/NYD/ZYD 等以 D 结尾的段（备查）
RETAIL_EXCL = re.compile(r"机构专享|私行|私享|私募|尊享|员工|定向")
OPEN_PAT = re.compile(r"日开|天天|活期|最短持有|最低持有|天持有|月持有|持有期|定开")
MANAGER = {
    "XY": "兴银", "GD": "光大", "HX": "华夏", "MS": "民生", "NY": "南银",
    "JY": "交银", "JX": "建信", "GY": "工银", "YC": "中邮", "ZY": "中银",
    "BY": "北银", "PY": "浦银", "PA": "平安", "NB": "宁银", "HY": "杭银",
    "ZX": "信银", "ZXPW": "信银(私募)", "SY": "苏银", "SH": "上银", "NJ": "农银",
    "CMBR": "招银(大额存单)", "SYD": "苏银(定向)", "NBD": "宁银(定向)",
    "JXD": "建信(定向)", "BYD": "北银(定向)", "NYD": "南银(定向)", "ZYD": "中银(定向)",
}


def pdate(s):
    try:
        return datetime.date.fromisoformat(str(s).split(" ")[0])
    except Exception:
        return None


def risk_of(p):
    raw = str(p.get("risk") or "").strip()
    m = re.search(r"R\d", raw)
    if m:
        return m.group(0)
    base = raw.split("(")[0].split("（")[0].strip()
    return RISK.get(base, base or "?")


def mgr_of(code):
    if re.fullmatch(r"[0-9]{4,6}[A-Z]?", code):
        return "招银理财"
    m = re.match(r"^([A-Za-z]+)", code)
    if not m:
        return "?"
    return MANAGER.get(m.group(1), m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="/tmp/cmb_catalog.json")
    ap.add_argument("--out", default="/tmp/cmb_full_cand.json")
    ap.add_argument("--max-days", type=int, default=180)
    ap.add_argument("--max-init", type=float, default=200000)
    a = ap.parse_args()

    prods = json.load(open(a.catalog, encoding="utf8"))
    today = datetime.date.today()
    rows = []
    stats = {"total": len(prods)}
    for p in prods:
        exp = pdate(p.get("expireDate"))
        if exp and exp < today:
            continue
        beg, end = pdate(p.get("beginDate")), pdate(p.get("endDate"))
        name = (p.get("prdBrief") or p.get("prdName") or "").strip()
        term = p.get("term") or ""
        risk = risk_of(p)
        if risk not in ("R1", "R2"):
            continue
        code = p["prdCode"]
        if PRIVATE_SEG.search(code):
            continue
        if RETAIL_EXCL.search(name):
            continue
        init = p.get("initMoney") or 0
        if init >= a.max_init:
            continue
        win = bool(beg and end and beg <= today <= end and beg.year >= today.year - 1)
        always = bool(OPEN_PAT.search(name) or OPEN_PAT.search(term))
        if not (win or always):
            continue
        if not (win or (beg and beg.year >= today.year - 2)):
            continue
        hd = hold_days(name, term)
        if hd is None or hd > a.max_days:
            continue
        rows.append(dict(code=code, name=name, risk=risk, term=term, hold=hd,
                         init=init, beg=beg.isoformat() if beg else "",
                         win=win, mgr=mgr_of(code),
                         style=p.get("style") or "", reg=p.get("regCode") or "",
                         self_run=bool(re.fullmatch(r"[0-9]{4,6}[A-Z]?", code)),
                         com=p.get("comNam") or ""))
    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"今天 {today}｜全目录 {len(prods)} 只")
    print(f"符合 R1/R2 + 持有期<= {a.max_days}天 + 起购< {a.max_init:.0f} 的: {len(rows)} 只")
    import collections
    print("按管理人:", dict(collections.Counter(r["mgr"] for r in rows)))
    print("按风险:", dict(collections.Counter(r["risk"] for r in rows)))
    print("按持有期:", dict(sorted(collections.Counter(r["hold"] for r in rows).items())))
    print(f"写入 {a.out}")


if __name__ == "__main__":
    main()
