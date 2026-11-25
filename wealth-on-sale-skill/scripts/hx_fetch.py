#!/usr/bin/env python3
"""华夏理财官网 hxwm.com.cn 历史净值抓取器
1) /common/js/gmjzbgData.js → 净值报告索引（10153 份，覆盖 8499 个产品）
2) 每份报告 address 指向一个 js，内含该期多份额净值行
输出: nav/hx/<productId>.json + nav/hx_products.json（产品主数据 gmcpxxData.json）
"""
import json, re, time, urllib.request, os, sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
OUT=os.path.join(os.path.dirname(__file__),"hx"); os.makedirs(OUT,exist_ok=True)
def get(url):
    from urllib.parse import quote
    url=quote(url,safe='/:?&=.')
    req=urllib.request.Request(url); req.add_header("User-Agent",UA)
    with urllib.request.urlopen(req,timeout=30) as r: return r.read().decode('utf8','replace')

def main(limit=None):
    raw=get("https://www.hxwm.com.cn/common/js/gmjzbgData.js")
    data=json.loads(re.search(r'jzbgData\s*=\s*(\[.*\])',raw,re.S).group(1))
    # 产品主数据
    try:
        raw2=get("https://www.hxwm.com.cn/common/js/gmcpxxData.json")
        prods=[json.loads(l) for l in raw2.splitlines() if l.strip()]
        json.dump(prods,open(os.path.join(OUT,"..","hx_products.json"),"w",encoding="utf8"),ensure_ascii=False)
        print("产品主数据:",len(prods))
    except Exception as e: print("prod data err",e)
    byid={}
    for r in data: byid.setdefault(r['id'],[]).append(r)
    print("覆盖产品:",len(byid),"报告:",len(data))
    ids=list(byid.keys())
    if limit: ids=ids[:limit]
    for i,pid in enumerate(ids):
        reports=byid[pid]
        try:
            allrows=[]
            for rep in reports:
                j=get("https://www.hxwm.com.cn"+rep['address'])
                allrows+=json.loads(j)
                time.sleep(0.15)
            json.dump({"productId":pid,"title":reports[0]['title'],"rows":allrows},
                      open(os.path.join(OUT,f"{pid}.json"),"w",encoding="utf8"),ensure_ascii=False)
            if (i+1)%50==0 or i+1==len(ids):
                print(f"[{i+1}/{len(ids)}] {pid} {reports[0]['title'][:24]} reports={len(reports)} rows={len(allrows)}",flush=True)
        except Exception as e:
            print(f"[{i+1}] {pid} ERR {str(e)[:80]}",flush=True)
        time.sleep(0.2)
    print("DONE",len(ids))

if __name__=="__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv)>1 else None)
