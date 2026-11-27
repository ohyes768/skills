"""拉取理财产品历史净值（仅招银自营 + 杭银自营）。

用法:
    python fetch_nav_history.py <code> [<code> ...] [--out data/nav_history]

- 招银自营 (4-6位数字可带字母，如 120053A): cfweb getSAValueByPage 全量分页
- 杭银理财 (TYG/JQB/HYG...): 官网 /eportal/hzbw/netval/<code>_netval.json
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
HERE = os.path.dirname(os.path.abspath(__file__))


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def is_cmb(code: str) -> bool:
    # 4-6位数字(可带份额字母)=招银自营销售代码（如 120053A、13265D）
    return bool(re.fullmatch(r"[0-9]{4,6}[A-Z]?", code.upper()))


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



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "nav_history"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    for code in args.codes:
        code = code.upper()
        try:
            rows = (fetch_cmb(code) if is_cmb(code)
                    else fetch_hz(code))
        except Exception as e:
            print(f"{code}: 拉取失败 {e}")
            continue
        if not rows:
            print(f"{code}: 0 点（接口无数据，可能代码不支持或未披露净值）")
            continue
        path = os.path.join(args.out, f"{code}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "nav"])
            w.writerows(rows)
        print(f"{code}: {len(rows)} 点  {rows[0][0]} -> {rows[-1][0]}  -> {path}")


if __name__ == "__main__":
    main()
