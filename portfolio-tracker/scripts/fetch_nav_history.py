"""拉取理财产品历史净值。

用法:
    python fetch_nav_history.py <code> [<code> ...] [--out nav_history]

- 杭银理财 (TYG/JQB/HYG...): 官网 /eportal/hzbw/netval/<code>_netval.json
- 信银理财 (AF/BF...): wechat.citic-wealth.com getTAProductNav (queryUnit=4 全量)
输出: <out>/<CODE>.csv  (date,nav)
"""
import argparse
import csv
import json
import os
import re
import ssl
import urllib.request

HZ_NETVAL = "https://www.hzbankwealth.cn/eportal/hzbw/netval/{}_netval.json"
CITIC_NAV = ("https://wechat.citic-wealth.com/cms.product/api/custom/"
             "productInfo/getTAProductNav")


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def is_citic(code: str) -> bool:
    return code[:2].upper() in ("AF", "BF")


def is_cmb(code: str) -> bool:
    # XY+6位=代销码；5位数字+字母=招银销售代码（如 13265D）
    return bool(re.fullmatch(r"(XY|GD)[0-9]{6}|[0-9]{4,6}[A-Z]?", code.upper()))


def fetch_cmb(code: str):
    """招行一网通 getSAValueByPage 分页拉全量净值。"""
    from code_convert import CmbResolver
    r = CmbResolver()
    lst = r._post("/ProductInfo/getProductByPrdCode", qs=f"prdCode={code.upper()}")
    d = (lst.get("body") or [None])[0]
    saa = d.get("saaCod") if d else None
    if not saa:
        raise RuntimeError("查无此代码或缺 saaCod")
    rows, page = [], 1
    while True:
        b = r._post("/ProductValue/getSAValueByPage",
                    {"saaCod": saa, "funCod": code.upper(),
                     "pageIndex": page, "pageSize": 100})
        data = (b.get("body") or {}).get("data") or []
        if not data:
            break
        for a in data:
            nd = str(a["znavDat"])
            rows.append((f"{nd[:4]}-{nd[4:6]}-{nd[6:]}", float(a["znavVal"])))
        total = b["body"].get("totalPage") or 1
        if page >= total:
            break
        page += 1
    return sorted(set(rows))


def fetch_hz(code: str):
    with urllib.request.urlopen(HZ_NETVAL.format(code), context=_ctx(),
                                timeout=30) as r:
        data = json.load(r)
    rows = [(x["net_value_date"], float(x["unit_net_value"])) for x in data]
    return sorted(rows)


def fetch_citic(code: str):
    from code_convert import _legacy_ssl_session
    s = _legacy_ssl_session()
    r = s.get(CITIC_NAV, params={"prodCode": code, "queryUnit": 4,
                                 "privateFlag": 1}, timeout=30)
    arr = r.json()["data"]["productNavPic"] or []
    rows = []
    for a in arr:
        d = str(a["navDate"])
        rows.append((f"{d[:4]}-{d[4:6]}-{d[6:]}", float(a["nav"])))
    return sorted(rows)


def fetch_ms(code: str):
    """民生理财官网 BTADailyQry 分页拉全量净值（先由招行码反查管理人代码）。"""
    from code_convert import MsResolver
    import requests as _rq

    ms_code = MsResolver().resolve(code).extra["ms_code"]
    h = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded",
         "Referer": "https://www.cmbcwm.com.cn/grlc/cpxq/"}
    rows, page = [], 1
    while True:
        r = _rq.post("https://www.cmbcwm.com.cn/gw/po_web/BTADailyQry", headers=h,
                     data={"chart_type": 1, "real_prd_code": ms_code,
                           "begin_date": "20000101", "end_date": "",
                           "pageNo": page, "pageSize": 100}, timeout=30)
        body = r.json()
        data = body.get("list") or []
        if not data:
            break
        for a in data:
            nd = str(a["ISS_DATE"])
            rows.append((f"{nd[:4]}-{nd[4:6]}-{nd[6:]}", float(a["NAV"])))
        total = body.get("totalSize") or 0
        if page * 100 >= total:
            break
        page += 1
    return sorted(set(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--out", default="nav_history")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for code in args.codes:
        code = code.upper()
        try:
            rows = (fetch_citic(code) if is_citic(code)
                    else fetch_cmb(code) if is_cmb(code)
                    else fetch_ms(code) if code.upper().startswith("MS")
                    else fetch_hz(code))
        except Exception as e:
            print(f"{code}: 拉取失败 {e}")
            continue
        path = os.path.join(args.out, f"{code}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "nav"])
            w.writerows(rows)
        print(f"{code}: {len(rows)} 点  {rows[0][0]} -> {rows[-1][0]}  -> {path}")


if __name__ == "__main__":
    main()
