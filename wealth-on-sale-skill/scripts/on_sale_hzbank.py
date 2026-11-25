#!/usr/bin/env python3
"""杭行代销第三方理财产品筛选（在售）

数据源: iibsp.hzbank.com.cn 财富产品信息查询平台（无需登录）
用法:
  python3 on_sale_hzbank.py                     # 全部在售（326只）
  python3 on_sale_hzbank.py --risk R2           # 按风险等级
  python3 on_sale_hzbank.py --manager 华夏       # 按管理人关键字
  python3 on_sale_hzbank.py --manager 光大,信银  # 多管理人
  python3 on_sale_hzbank.py --min-days 30       # 最短持有期≥30天
  python3 on_sale_hzbank.py --json              # JSON 输出
"""
import argparse, json, sys, time, urllib.request

API="https://iibsp.hzbank.com.cn/IntegratedServer/queryLcProdInfoList"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"

def fetch_page(page,size=100):
    payload={"channelCode":"0188","systemCode":"ISMS0001","transCode":"ISSW0001",
             "requestBody":{"prdCode":"","prdName":"","wealthProdType":"1",
                            "pageSize":size,"currentNum":page}}
    req=urllib.request.Request(API,data=json.dumps(payload).encode(),method="POST")
    req.add_header("User-Agent",UA); req.add_header("Content-Type","application/json")
    for a in range(3):
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                return json.load(r)["data"]["responseBody"]
        except Exception:
            if a==2: raise
            time.sleep(2)

def fetch_all():
    d=fetch_page(1)
    total=d.get("total",0)
    rows=d.get("content") or []
    p=2
    while len(rows)<total:
        time.sleep(0.3)
        d=fetch_page(p)
        rows+=d.get("content") or []
        p+=1
    return rows

def main():
    ap=argparse.ArgumentParser(description="杭行代销第三方在售理财筛选")
    ap.add_argument("--risk",help="风险等级过滤: R1,R2,R3...")
    ap.add_argument("--manager",help="管理人关键字(逗号分隔)")
    ap.add_argument("--min-days",type=int,help="产品期限≥N天")
    ap.add_argument("--json",action="store_true",help="JSON 输出")
    args=ap.parse_args()

    print("正在拉取杭行代销在售产品...",file=sys.stderr)
    rows=fetch_all()
    # 只留在售
    rows=[r for r in rows if r.get("saleDurationFlag")=="在售"]
    # 风险过滤
    if args.risk:
        risks=[x.strip().replace("R","") for x in args.risk.split(",")]
        rows=[r for r in rows if str(r.get("riskLevel","")) in risks]
    # 管理人过滤
    if args.manager:
        kws=[x.strip() for x in args.manager.split(",")]
        rows=[r for r in rows if any(k in r.get("taName","") for k in kws)]
    # 期限过滤
    if args.min_days:
        rows=[r for r in rows if (r.get("prodTerm") or 0)>=args.min_days]

    if args.json:
        print(json.dumps(rows,ensure_ascii=False,indent=1))
        return

    # 表格输出
    print(f"\n杭行代销第三方在售: {len(rows)} 只\n")
    print(f"{'产品代码':<14}{'管理人':<12}{'风险':<5}{'期限(天)':<8}{'起购':<10}{'产品名称'}")
    print("-"*95)
    for r in sorted(rows,key=lambda x:(x.get("riskLevel") or 0,x.get("prodTerm") or 0)):
        code=r.get("prdCode","")
        ta=r.get("taName","").replace("有限责任公司","")
        risk=f"R{r.get('riskLevel','')}"
        term=str(r.get("prodTerm",""))
        amt=str(r.get("iniAmount",""))
        name=r.get("prdName","")[:36]
        print(f"{code:<14}{ta:<12}{risk:<5}{term:<8}{amt:<10}{name}")

    # 按管理人汇总
    from collections import Counter
    print(f"\n按管理人:")
    for k,v in Counter(r["taName"].replace("有限责任公司","") for r in rows).most_common():
        print(f"  {k}: {v}")

if __name__=="__main__":
    main()
