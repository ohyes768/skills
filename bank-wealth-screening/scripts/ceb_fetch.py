#!/usr/bin/env python3
"""光大银行(代销光大理财)历史净值抓取器
数据源: www.95595.com.cn eportal portlet 接口
输出: nav/ceb/<CPCODE>.json + nav/ceb_index.csv
"""
import json, time, urllib.request, csv, os, sys

BASE="http://www.95595.com.cn"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
OUT=os.path.join(os.path.dirname(__file__),"ceb")
os.makedirs(OUT,exist_ok=True)

def http(url,data=None,timeout=30):
    h={"User-Agent":UA,"Referer":BASE+"/site/gsyw/dglc/148443261/index.html"}
    if data is not None:
        h["Content-Type"]="application/x-www-form-urlencoded"
        h["X-Requested-With"]="XMLHttpRequest"
    req=urllib.request.Request(url,data=data.encode() if data else None,method="POST" if data else "GET",headers=h)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r: return r.read().decode('utf8','replace')
        except Exception as e:
            if attempt==2: raise
            time.sleep(2)

def fetch_list():
    raw=http(BASE+"/eportal/ui?moduleId=5&portal.url=/portlet/yglc!findDGProductLatestNetValueList.portlet")
    return json.loads(raw)

def fetch_hist(code,start="20200101",end="20261231"):
    raw=http(BASE+"/eportal/ui?moduleId=5&portal.url=/portlet/yglc!getLsjz.portlet",
             f"cpcode={code}&jzrqStart={start}&jzrqEnd={end}")
    d=json.loads(raw)
    return d.get("cpname"), d.get("lsjzMap") or []

def main(limit=None, days=("20200101","20261231")):
    prods=fetch_list()
    if limit: prods=prods[:limit]
    index=[]
    for i,p in enumerate(prods):
        code=p["cpCode"]; name=p["title"]; status=p.get("cpztmc")
        try:
            name2,rows=fetch_hist(code,*days)
            if name2: name=name2
            path=os.path.join(OUT,f"{code}.json")
            json.dump({"cpCode":code,"name":name,"status":status,"rows":rows},open(path,"w",encoding="utf8"),ensure_ascii=False)
            index.append({"cpCode":code,"name":name,"status":status,"rows":len(rows)})
            print(f"[{i+1}/{len(prods)}] {code} {name[:24]} rows={len(rows)}",flush=True)
        except Exception as e:
            index.append({"cpCode":code,"name":name,"status":status,"rows":0,"err":str(e)[:80]})
            print(f"[{i+1}] {code} ERR {e}",flush=True)
        time.sleep(0.8)
    with open(os.path.join(OUT,"..","ceb_index.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=["cpCode","name","status","rows","err"]); w.writeheader(); w.writerows(index)
    ok=sum(1 for r in index if r.get("rows",0)>0)
    print(f"DONE ok={ok}/{len(index)}")

if __name__=="__main__":
    import sys
    limit=int(sys.argv[1]) if len(sys.argv)>1 else None
    main(limit=limit)
