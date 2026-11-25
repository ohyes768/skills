#!/usr/bin/env python3
"""兴银理财 www.cibwm.com.cn 历史净值抓取器
列表: POST /api/public/pc/productInfo/getProdInfoByPage  (8126只, 分页 page.pageNumber/pageSize)
净值: GET  /api/public/pc/productVal/performanceTrend/<productCode>/SINCE
输出: nav/xy/<productCode>.json + nav/xy_index.csv
"""
import json, time, urllib.request, csv, os, sys

BASE="https://www.cibwm.com.cn/api"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
OUT=os.path.join(os.path.dirname(__file__),"xy"); os.makedirs(OUT,exist_ok=True)

def http(url,data=None,timeout=30):
    h={"User-Agent":UA,"Referer":BASE.replace('/api','')+"/personal-products","Content-Type":"application/json"}
    req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,
                               method="POST" if data is not None else "GET",headers=h)
    for a in range(3):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r: return json.load(r)
        except Exception:
            if a==2: raise
            time.sleep(2)

def fetch_list(page=1,size=200,status=""):
    payload={"page":{"pageNumber":page,"pageSize":size,"orders":[]},
             "pageFilterCriteria":{"preferredTypeKey":[],"riskLevel":[],"productPeriod":[],
             "productType1":[],"productStatus":[] or [status] if status else [],"productForm":[],
             "orgType":[],"saleCurrency":[],"distributionChannel":[],"selectionLabel":[],"fuzzyStr":""}}
    d=http(f"{BASE}/public/pc/productInfo/getProdInfoByPage",payload)
    return d["data"]

def fetch_trend(code):
    d=http(f"{BASE}/public/pc/productVal/performanceTrend/{code}/SINCE")
    return (d.get("data") or {}).get("list") or []

def main(limit_products=None, page_size=100):
    # 先拉全量产品列表
    p=1; prods=[]
    while True:
        d=fetch_list(p,page_size); lst=d.get("list") or []
        prods+=lst
        print(f"list page {p}: +{len(lst)} total={d.get('total')}",flush=True)
        if len(lst)<page_size or p*page_size>=d.get("total",0): break
        p+=1; time.sleep(0.4)
    json.dump(prods,open(os.path.join(OUT,"..","xy_products.json"),"w",encoding="utf8"),ensure_ascii=False)
    print("products:",len(prods))
    if limit_products: prods=prods[:limit_products]
    index=[]
    for i,pr in enumerate(prods):
        code=pr.get("productCode")
        if not code: continue
        try:
            rows=fetch_trend(code)
            json.dump({"productCode":code,"productName":pr.get("productName"),
                       "riskLevel":pr.get("riskLevel"),"productStatus":pr.get("productStatus"),
                       "rows":rows},open(os.path.join(OUT,f"{code}.json"),"w",encoding="utf8"),ensure_ascii=False)
            index.append({"productCode":code,"name":pr.get("productName"),"status":pr.get("productStatus"),"rows":len(rows)})
            if (i+1)%10==0 or i+1==len(prods): print(f"[{i+1}/{len(prods)}] {code} rows={len(rows)}",flush=True)
        except Exception as e:
            index.append({"productCode":code,"name":pr.get("productName"),"status":pr.get("productStatus"),"rows":0,"err":str(e)[:80]})
        time.sleep(0.3)
    with open(os.path.join(OUT,"..","xy_index.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["productCode","name","status","rows","err"]); w.writeheader(); w.writerows(index)
    print("DONE ok=",sum(1 for r in index if r.get("rows",0)>0),"/",len(index))

if __name__=="__main__":
    main(limit_products=int(sys.argv[1]) if len(sys.argv)>1 else None)
