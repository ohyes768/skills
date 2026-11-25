#!/usr/bin/env python3
"""民生理财结构化历史净值（cmbcwm.com.cn BTADailyQry）
用法: python3 ms_nav_fetch.py <real_prd_code> [<real_prd_code>...]
     或 python3 ms_nav_fetch.py --name "天天增利"  # 按名称搜索产品再拉净值
输出: nav/ms_nav/<REAL_PRD_CODE>.json
"""
import json, urllib.request, urllib.parse, os, sys, time
BASE="https://www.cmbcwm.com.cn/gw/po_web"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
REF="https://www.cmbcwm.com.cn/cmbcwm/grlc/index.html"
OUT=os.path.join(os.path.dirname(__file__),"ms_nav"); os.makedirs(OUT,exist_ok=True)

def post_form(url,payload):
    data=urllib.parse.urlencode(payload).encode()
    req=urllib.request.Request(url,data=data,method="POST")
    req.add_header("User-Agent",UA); req.add_header("Content-Type","application/x-www-form-urlencoded")
    req.add_header("Referer",REF)
    for a in range(3):
        try:
            with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
        except Exception:
            if a==2: raise
            time.sleep(2)

def search_products(name):
    d=post_form(f"{BASE}/BTAProductQry",{"prd_type":0,"pageNo":1,"pageSize":100,"code_or_name":name})
    return d.get("list") or []

def fetch_nav(real_code):
    rows=[]; page=1
    while True:
        d=post_form(f"{BASE}/BTADailyQry",{"chart_type":1,"real_prd_code":real_code,
                     "begin_date":"20000101","end_date":"","pageNo":page,"pageSize":100})
        lst=d.get("list") or []
        if not lst: break
        for a in lst:
            nd=str(a.get("ISS_DATE",""))
            rows.append({"date":f"{nd[:4]}-{nd[4:6]}-{nd[6:]}",
                         "nav":float(a["NAV"]),
                         "tot_nav":float(a.get("TOT_NAV") or 0),
                         "income":a.get("INCOME"),
                         "seven_day":a.get("WEEK_CLIENTRATE")})
        if page*100>=d.get("totalSize",0): break
        page+=1; time.sleep(0.3)
    return sorted(rows,key=lambda x:x["date"])

def main():
    if sys.argv[1]=="--name":
        # 搜索产品并逐只拉净值
        prods=search_products(sys.argv[2])
        print(f"搜索'{sys.argv[2]}': {len(prods)} 只")
        for p in prods:
            code=p["REAL_PRD_CODE"]
            name=p.get("PRD_NAME") or p.get("PRD_SHORT_NAME") or ""
            rows=fetch_nav(code)
            json.dump({"realPrdCode":code,"name":name,"rows":rows},
                      open(os.path.join(OUT,f"{code}.json"),"w",encoding="utf8"),ensure_ascii=False)
            print(f"  {code} {name[:30]} -> {len(rows)} 条")
        return
    # 直接按 real_prd_code
    for code in sys.argv[1:]:
        if code.startswith("-"):  # 防止把 --help 等参数当产品码抓取
            print(f"跳过非法代码 {code}")
            continue
        rows=fetch_nav(code)
        json.dump({"realPrdCode":code,"rows":rows},
                  open(os.path.join(OUT,f"{code}.json"),"w",encoding="utf8"),ensure_ascii=False)
        print(f"{code} -> {len(rows)} 条")

if __name__=="__main__":
    main()
