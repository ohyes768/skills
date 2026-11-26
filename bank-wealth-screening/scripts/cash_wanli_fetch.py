"""现金管理类（七日年化型）业绩口径：民生 BTADailyQry 的 WEEK_CLIENTRATE。

用法: python3 cash_wanli_fetch.py <REAL_PRD_CODE> [<REAL_PRD_CODE>...]
输出: scripts/ms_nav/<code>.json  (含 rows[].seven_day，nav_stats 兼容)
      并打印七日年化 -> 年化估算

年化换算: 七日年化 r7 -> 年化 ≈ (1 + r7/7)^365 - 1  （按复利）
         或简单口径 (1 + r7)^(365/7) - 1
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.cmbcwm.com.cn/gw/po_web"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
REF = "https://www.cmbcwm.com.cn/cmbcwm/grlc/index.html"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms_nav")
os.makedirs(OUT, exist_ok=True)


def post_form(url, payload):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Referer", REF)
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if a == 2:
                raise
            time.sleep(2)


def search_products(name):
    d = post_form(f"{BASE}/BTAProductQry",
                   {"prd_type": 0, "pageNo": 1, "pageSize": 100, "code_or_name": name})
    return d.get("list") or []


def fetch_nav(real_code):
    rows, page = [], 1
    while True:
        d = post_form(f"{BASE}/BTADailyQry",
                       {"chart_type": 1, "real_prd_code": real_code,
                        "begin_date": "20000101", "end_date": "",
                        "pageNo": page, "pageSize": 100})
        lst = d.get("list") or []
        if not lst:
            break
        for a in lst:
            nd = str(a.get("ISS_DATE", ""))
            rows.append({"date": f"{nd[:4]}-{nd[4:6]}-{nd[6:]}",
                         "nav": float(a["NAV"]),
                         "tot_nav": float(a.get("TOT_NAV") or 0),
                         "seven_day": a.get("WEEK_CLIENTRATE")})
        if page * 100 >= d.get("totalSize", 0):
            break
        page += 1
        time.sleep(0.3)
    return sorted(rows, key=lambda x: x["date"])


def annualize_from_seven(r7):
    """WEEK_CLIENTRATE 本身已是七日年化率，直接用；万份收益推算与之吻合（实测 0.65%~0.93% vs 0.84%）。"""
    return r7


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--name":
        prods = search_products(sys.argv[2])
        print(f"搜索'{sys.argv[2]}': {len(prods)} 只")
        for p in prods:
            code = p["REAL_PRD_CODE"]
            name = p.get("PRD_NAME") or p.get("PRD_SHORT_NAME") or ""
            rows = fetch_nav(code)
            json.dump({"realPrdCode": code, "name": name, "rows": rows},
                      open(os.path.join(OUT, f"{code}.json"), "w", encoding="utf8"),
                      ensure_ascii=False)
            last7 = rows[-1]["seven_day"] if rows else None
            print(f"  {code} {name[:32]} -> {len(rows)} 条, 最新七日年化 {last7}, "
                  f"年化≈{annualize_from_seven(last7):.4%}" if last7 else
                  f"  {code} {name[:32]} -> {len(rows)} 条")
    else:
        for code in sys.argv[1:]:
            if code.startswith("-"):
                continue
            rows = fetch_nav(code)
            json.dump({"realPrdCode": code, "rows": rows},
                      open(os.path.join(OUT, f"{code}.json"), "w", encoding="utf8"),
                      ensure_ascii=False)
            last7 = rows[-1]["seven_day"] if rows else None
            print(f"{code} -> {len(rows)} 条, 最新七日年化 {last7}, "
                  f"年化≈{annualize_from_seven(last7):.4%}" if last7 else f"{code} -> {len(rows)} 条")
