"""兴银理财现金管理类七日年化：按期号+份额字母匹配 performanceTrend 的 sevenDayAnnualized。

兴银产品代码形如 9TTL971N = 添利天天利71号 N份额；招行货架上 XY030170 = 兴银理财兴银添利天天利71号B。
用法: python3 fill_cash_xy.py --cand /tmp/cmb_full_refs4.json --out /tmp/cmb_full_refs5.json
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

BASE = "https://www.cibwm.com.cn/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xy")


def http_json(url, payload=None):
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/json")
    req.add_header("Referer", "https://www.cibwm.com.cn/personal-products")
    for a in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf8", "replace"))
        except Exception:
            if a == 2:
                raise
            time.sleep(2)


def search(fuzzy):
    payload = {"page": {"pageNumber": 1, "pageSize": 100, "orders": []},
               "pageFilterCriteria": {"preferredTypeKey": [], "riskLevel": [], "productPeriod": [],
                                      "productType1": [], "productStatus": [], "productForm": [],
                                      "orgType": [], "saleCurrency": [], "distributionChannel": [],
                                      "selectionLabel": [], "fuzzyStr": fuzzy}}
    d = http_json(f"{BASE}/public/pc/productInfo/getProdInfoByPage", payload)
    return (d.get("data") or {}).get("list") or []


def trend(code):
    d = http_json(f"{BASE}/public/pc/productVal/performanceTrend/{code}/SINCE")
    return (d.get("data") or {}).get("list") or []


def key_of(prod_name, product_code):
    """(期号, 份额字母) -> 兴银产品。"""
    m = re.search(r"(\d+)号", prod_name or "")
    if not m:
        return None
    num = m.group(1)
    tail = (product_code or "")[-1] if product_code else ""
    return (num, tail)


def search_all(fuzzy, page_size=100, max_pages=30):
    """兴银搜索接口 pageSize 会被服务端截断（要 100 返 100，但翻到第 8 页起返回空），
    需并行翻页才能拿全。"""
    from concurrent.futures import ThreadPoolExecutor

    def one(p):
        payload = {"page": {"pageNumber": p, "pageSize": page_size, "orders": []},
                   "pageFilterCriteria": {"preferredTypeKey": [], "riskLevel": [], "productPeriod": [],
                                          "productType1": [], "productStatus": [], "productForm": [],
                                          "orgType": [], "saleCurrency": [], "distributionChannel": [],
                                          "selectionLabel": [], "fuzzyStr": fuzzy}}
        try:
            d = http_json(f"{BASE}/public/pc/productInfo/getProdInfoByPage", payload)
            data = d.get("data") or {}
            return data.get("list") or [], data.get("total") or 0
        except Exception:
            return [], 0

    out, total = [], 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(one, range(1, max_pages + 1)))
    for lst, t in res:
        out += lst
        total = max(total, t)
    seen, uniq = set(), []
    for p in out:
        c = p.get("productCode")
        if c and c not in seen:
            seen.add(c)
            uniq.append(p)
    return uniq, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs4.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs5.json")
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))
    xy = [r for r in rows if r["mgr"] == "兴银"
          and not r.get("cash_metrics") and not r.get("seven_day")]
    print(f"兴银待补: {len(xy)}")

    # 搜一次，索引 (期号, 份额字母)
    idx = {}
    for fuzzy in ["添利天天利", "稳利安盈", "稳利恒盈", "添利"]:
        try:
            prods, total = search_all(fuzzy)
            print(f"  搜索 {fuzzy}: total={total} got={len(prods)}")
            for p in prods:
                k = key_of(p.get("productName"), p.get("productCode"))
                if k:
                    idx.setdefault(k, p)
        except Exception as e:
            print(f"  搜索 {fuzzy} 失败: {str(e)[:60]}")
    print(f"  兴银索引 {len(idx)} 支")

    os.makedirs(OUT, exist_ok=True)
    hit = 0
    for r in xy:
        m = re.search(r"(\d+)号([A-Z])?$", r["name"])
        if not m:
            continue
        num = m.group(1)
        tail = m.group(2) or ""
        p = idx.get((num, tail))
        if not p:
            continue
        code = p.get("productCode")
        try:
            rowsdata = trend(code)
        except Exception:
            continue
        if not rowsdata:
            continue
        sds = [(x.get("dataDt", "")[:10], x.get("sevenDayAnnualized"))
                for x in rowsdata if x.get("sevenDayAnnualized")]
        if len(sds) < 30:
            continue
        # 兴银的 sevenDayAnnualized 是"百分数数值"（0.8926 表示 0.8926%），
        # 与民生/信银的小数口径不同 —— 用 effIopv(万份收益)推算的日收益年化
        # (0.904%) 与 0.8926 吻合，据此 /100 归一为小数。
        vals = [float(v) / 100.0 for _, v in sds]
        last30 = vals[-30:]
        last90 = vals[-90:]
        json.dump({"productCode": code, "productName": p.get("productName"),
                   "riskLevel": p.get("riskLevel"), "rows": rowsdata},
                  open(os.path.join(OUT, f"{code}.json"), "w", encoding="utf8"),
                  ensure_ascii=False)
        r["seven_day"] = dict(latest=vals[-1], avg30=sum(last30) / len(last30),
                              avg90=sum(last90) / len(last90), n=len(vals),
                              start=sds[0][0], end=sds[-1][0])
        r["seven_day_ref"] = f"{code} {p.get('productName','')[:26]}"
        hit += 1
    print(f"  匹配到七日年化: {hit}/{len(xy)}")
    for r in xy[:8]:
        sd = r.get("seven_day")
        if sd:
            print(f"    {r['code']:<10} {r['name'][:30]:<32} 最新{sd['latest']:.4%} "
                  f"均90日{sd['avg90']:.4%} [{sd['start']}~{sd['end']}]")
    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"写入 {a.out}")


if __name__ == "__main__":
    main()
