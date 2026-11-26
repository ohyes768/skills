"""探测各管理人现金管理类的七日年化数据源。

逐个试探已知接口，看哪个能返回七日年化/万份收益。
用法: python3 probe_cash_sources.py
"""
import json
import ssl
import sys
import urllib.parse
import urllib.request

UA_DESK = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
UA_MOB = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"


def get(url, ua=UA_DESK, headers=None):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", ua)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf8", "replace")


def post_json(url, payload, ua=UA_DESK):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("User-Agent", ua)
    req.add_header("Content-Type", "application/json")
    req.add_header("Referer", "https://www.cibwm.com.cn/personal-products")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf8", "replace"))


def probe_ningbo():
    """宁银理财：nigl.com.cn？"""
    urls = [
        "https://www.nigl.com.cn/",
        "https://www.ningbobl.com/",
    ]
    for u in urls:
        try:
            h = get(u)
            print(f"  宁银 {u}: {len(h)} 字节, 命中'七日':{'七日' in h}")
        except Exception as e:
            print(f"  宁银 {u}: ERR {str(e)[:60]}")


def probe_pingan():
    """平安理财：bank.pingan.com 或 平安资管"""
    urls = [
        "https://bank.pingan.com/",
        "https://ly.pingan.com/",
    ]
    for u in urls:
        try:
            h = get(u)
            print(f"  平安 {u}: {len(h)} 字节")
        except Exception as e:
            print(f"  平安 {u}: ERR {str(e)[:60]}")


def probe_boc():
    """中银理财：bocwealth.com / bankofchina"""
    for u in ["https://www.bocwealth.com/", "https://www.boc.cn/"]:
        try:
            h = get(u)
            print(f"  中银 {u}: {len(h)} 字节")
        except Exception as e:
            print(f"  中银 {u}: ERR {str(e)[:60]}")


def probe_xy_yield():
    """兴银：试 productVal 下其他接口"""
    BASE = "https://www.cibwm.com.cn/api"
    cands = [
        "/public/pc/productVal/yieldTrend/{code}",
        "/public/pc/productVal/sevenDayYield/{code}",
        "/public/pc/productVal/productYield/{code}",
        "/public/pc/productInfo/getProductDetailByCode/{code}",
    ]
    code = "9A26508A"
    for c in cands:
        try:
            d = post_json(BASE + c.format(code=code), {})
            print(f"  兴银 {c}: {json.dumps(d, ensure_ascii=False)[:220]}")
        except Exception as e:
            print(f"  兴银 {c}: ERR {str(e)[:70]}")


def probe_xy_list():
    """兴银：getProdInfoByPage 返回里有没有七日年化字段"""
    payload = {"page": {"pageNumber": 1, "pageSize": 3, "orders": []},
               "pageFilterCriteria": {"preferredTypeKey": [], "riskLevel": [], "productPeriod": [],
                                      "productType1": [], "productStatus": [], "productForm": [],
                                      "orgType": [], "saleCurrency": [], "distributionChannel": [],
                                      "selectionLabel": [], "fuzzyStr": "稳利安盈"}}
    d = post_json("https://www.cibwm.com.cn/api/public/pc/productInfo/getProdInfoByPage", payload)
    lst = (d.get("data") or {}).get("list") or []
    if lst:
        print("  兴银 list 字段:", sorted(lst[0].keys()))


if __name__ == "__main__":
    print("== 兴银")
    probe_xy_list()
    probe_xy_yield()
    print("== 宁银")
    probe_ningbo()
    print("== 平安")
    probe_pingan()
    print("== 中银")
    probe_boc()
