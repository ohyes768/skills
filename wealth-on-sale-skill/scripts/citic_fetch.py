#!/usr/bin/env python3
"""信银理财 citic-wealth.com 历史净值抓取器
产品搜索: GET wechat.citic-wealth.com/cms.product/api/custom/productInfo/search?key=
净值:     GET wechat.citic-wealth.com/cms.product/api/custom/productInfo/getTAProductNav?prodCode=&queryUnit=1&privateFlag=1
注意: 服务器要求 UnsafeLegacyRenegotiation (TLS)，需 OPENSSL_CONF
输出: nav/citic/<prodCode>.json + nav/citic_index.csv
"""
import json, time, urllib.request, urllib.parse, csv, os, sys, subprocess, tempfile

BASE="https://wechat.citic-wealth.com"
UA="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"
OUT=os.path.join(os.path.dirname(__file__),"citic"); os.makedirs(OUT,exist_ok=True)

import ssl as _ssl
CTX=_ssl.create_default_context()
CTX.options |= 0x4  # SSL_OP_LEGACY_UNSAFE_RENEGOTIATION
_OPENER=urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))

def get(path,params):
    q=urllib.parse.urlencode(params)
    req=urllib.request.Request(f"{BASE}{path}?{q}")
    req.add_header("User-Agent",UA)
    req.add_header("Referer","https://www.citic-wealth.com/wechat/product/")
    for a in range(3):
        try:
            with _OPENER.open(req,timeout=30) as r: return json.load(r)
        except Exception:
            if a==2: raise
            time.sleep(2)

def search_all():
    """全量产品：search 接口一次返回全部"""
    d=get("/cms.product/api/custom/productInfo/search",{"key":"信银理财"})
    return d.get("data") or []

def fetch_nav(code):
    d=get("/cms.product/api/custom/productInfo/getTAProductNav",
          {"prodCode":code,"queryUnit":"1","privateFlag":"1"})
    if d.get("code") not in ("0000",200): return []
    data=d.get("data") or {}
    return data.get("productNavList") or []

def main(limit=None):
    prods=search_all()
    json.dump(prods,open(os.path.join(OUT,"..","citic_products.json"),"w",encoding="utf8"),ensure_ascii=False)
    print("products:",len(prods))
    if limit: prods=prods[:limit]
    index=[]
    for i,p0 in enumerate(prods):
        code=p0.get("fundCode") or p0.get("prodCode")
        if not code: continue
        try:
            rows=fetch_nav(code)
            json.dump({"prodCode":code,"name":p0.get("fundName"),"riskLevel":p0.get("riskLevelStr"),
                       "state":p0.get("fundStateStr"),"rows":rows},
                      open(os.path.join(OUT,f"{code}.json"),"w",encoding="utf8"),ensure_ascii=False)
            index.append({"prodCode":code,"name":p0.get("fundName"),"state":p0.get("fundStateStr"),"rows":len(rows)})
            if (i+1)%10==0 or i+1==len(prods): print(f"[{i+1}/{len(prods)}] {code} rows={len(rows)}",flush=True)
        except Exception as e:
            index.append({"prodCode":code,"name":p0.get("fundName"),"state":p0.get("fundStateStr"),"rows":0,"err":str(e)[:80]})
        time.sleep(0.3)
    with open(os.path.join(OUT,"..","citic_index.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["prodCode","name","state","rows","err"]); w.writeheader(); w.writerows(index)
    print("DONE ok=",sum(1 for r in index if r.get("rows",0)>0),"/",len(index))

if __name__=="__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv)>1 else None)
