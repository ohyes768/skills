"""代销产品：在各管理人官网按产品名搜代码，再拉历史净值，缓存到 scripts/<mgmt>/ 下。

用法: python3 fetch_dist_nav.py GD100010 "光大理财阳光金增利稳健日开15号D" ...
输出: scripts/<mgmt_dir>/<code>.json  (格式与各 fetcher 一致，nav_stats 可直接读)
"""
import json, os, ssl, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA_DESK = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
UA_MOB = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"

_ctx = ssl.create_default_context()
_ctx.options |= 0x4  # legacy renegotiation (信银)
_opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx))
_ctx2 = ssl.create_default_context()
_ctx2.check_hostname = False
_ctx2.verify_mode = ssl.CERT_NONE


def get(url, headers=None, insecure=False):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA_DESK)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    op = _opener.open(req, timeout=30)
    return op.read().decode("utf8", "replace")


def get_json(url, headers=None):
    return json.loads(get(url, headers))


# ---- 光大: 95595.com.cn eportal ----
def ceb_search(name):
    """光大列表接口返回母行产品；按名称过滤，返回 (cpCode, name) 列表"""
    raw = get("http://www.95595.com.cn/eportal/ui?moduleId=5&portal.url=/portlet/yglc!findDGProductLatestNetValueList.portlet",
              {"Referer": "http://www.95595.com.cn/site/gsyw/dglc/148443261/index.html",
               "X-Requested-With": "XMLHttpRequest"})
    prods = json.loads(raw)
    out = []
    for p in prods:
        nm = p.get("title") or ""
        if name in nm:
            out.append((p["cpCode"], nm))
    return out


def ceb_hist(code, start="20200101", end="20261231"):
    """光大历史净值（母行 100 只内才有）"""
    data = urllib.parse.urlencode({"cpcode": code, "jzrqStart": start, "jzrqEnd": end}).encode()
    req = urllib.request.Request(
        "http://www.95595.com.cn/eportal/ui?moduleId=5&portal.url=/portlet/yglc!getLsjz.portlet",
        data=data, method="POST")
    req.add_header("User-Agent", UA_DESK)
    req.add_header("Referer", "http://www.95595.com.cn/site/gsyw/dglc/148443261/index.html")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf8", "replace"))
    return d.get("lsjzMap") or []


# ---- 通用: 信银 search ----
def citic_search(name):
    q = urllib.parse.urlencode({"key": name})
    url = f"https://wechat.citic-wealth.com/cms.product/api/custom/productInfo/search?{q}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA_MOB)
    req.add_header("Referer", "https://www.citic-wealth.com/wechat/product/")
    d = json.loads(_opener.open(req, timeout=30).read().decode())
    return d.get("data") or []


def citic_nav(code):
    q = urllib.parse.urlencode({"prodCode": code, "queryUnit": "1", "privateFlag": "1"})
    url = f"https://wechat.citic-wealth.com/cms.product/api/custom/productInfo/getTAProductNav?{q}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA_MOB)
    req.add_header("Referer", "https://www.citic-wealth.com/wechat/product/")
    d = json.loads(_opener.open(req, timeout=30).read().decode())
    return d.get("data") or {}


# ---- 民生 ----
def ms_search(name):
    from urllib.parse import urlencode
    data = urlencode({"prd_type": 0, "pageNo": 1, "pageSize": 100, "code_or_name": name}).encode()
    req = urllib.request.Request("https://www.cmbcwm.com.cn/gw/po_web/BTAProductQry", data=data, method="POST")
    req.add_header("User-Agent", UA_DESK)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Referer", "https://www.cmbcwm.com.cn/cmbcwm/grlc/index.html")
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode()).get("list") or []


def ms_nav(real_code):
    from urllib.parse import urlencode
    rows, page = [], 1
    while True:
        data = urlencode({"chart_type": 1, "real_prd_code": real_code, "begin_date": "20000101",
                          "end_date": "", "pageNo": page, "pageSize": 100}).encode()
        req = urllib.request.Request("https://www.cmbcwm.com.cn/gw/po_web/BTADailyQry", data=data, method="POST")
        req.add_header("User-Agent", UA_DESK)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("Referer", "https://www.cmbcwm.com.cn/cmbcwm/grlc/index.html")
        d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        lst = d.get("list") or []
        if not lst:
            break
        for a in lst:
            nd = str(a.get("ISS_DATE", ""))
            rows.append({"date": f"{nd[:4]}-{nd[4:6]}-{nd[6:]}", "nav": float(a["NAV"]),
                         "tot_nav": float(a.get("TOT_NAV") or 0)})
        if page * 100 >= d.get("totalSize", 0):
            break
        page += 1
        time.sleep(0.3)
    return rows


# ---- 兴银 ----
def xy_search(name):
    payload = {"page": {"pageNumber": 1, "pageSize": 20, "orders": []},
               "pageFilterCriteria": {"preferredTypeKey": [], "riskLevel": [], "productPeriod": [],
                                      "productType1": [], "productStatus": [], "productForm": [],
                                      "orgType": [], "saleCurrency": [], "distributionChannel": [],
                                      "selectionLabel": [], "fuzzyStr": name}}
    url = "https://www.cibwm.com.cn/api/public/pc/productInfo/getProdInfoByPage"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("User-Agent", UA_DESK)
    req.add_header("Content-Type", "application/json")
    req.add_header("Referer", "https://www.cibwm.com.cn/personal-products")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    return (d.get("data") or {}).get("list") or []


def xy_nav(code):
    url = f"https://www.cibwm.com.cn/api/public/pc/productVal/performanceTrend/{code}/SINCE"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA_DESK)
    req.add_header("Referer", "https://www.cibwm.com.cn/personal-products")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    return (d.get("data") or {}).get("list") or []


# ---- 华夏 ----
def hx_search(name):
    import re
    raw = get("https://www.hxwm.com.cn/common/js/gmjzbgData.js")
    data = json.loads(re.search(r"jzbgData\s*=\s*(\[.*\])", raw, re.S).group(1))
    hits = []
    for r in data:
        t = r.get("title", "")
        if name in t:
            hits.append((r["id"], t, r["address"]))
    return hits


def hx_nav(product_id, addresses):
    import re
    allrows = []
    for addr in addresses:
        raw = get("https://www.hxwm.com.cn" + addr)
        allrows += json.loads(raw)
        time.sleep(0.15)
    return allrows


if __name__ == "__main__":
    print(json.dumps({"hint": "import this module"}, ensure_ascii=False))
