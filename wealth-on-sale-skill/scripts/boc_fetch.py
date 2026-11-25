#!/usr/bin/env python3
"""中银理财：中行净值频道 静态页解析
index_2217.json -> 每只产品详情页 -> document.write 的历史净值行
输出: nav/boc/<code>.json
"""
import json, re, time, urllib.request, os, sys
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
OUT=os.path.join(os.path.dirname(__file__),"boc"); os.makedirs(OUT,exist_ok=True)
def http(url):
    req=urllib.request.Request(url)
    req.add_header("User-Agent",UA)
    with urllib.request.urlopen(req,timeout=30) as r: return r.read().decode('utf8','replace')
def parse(html):
    # 每个产品块: document.write('<td...>VALUE</td>') 序列，按 </tr> 分组
    vals=re.findall(r"document\.write\('<td[^>]*>(.*?)</td>'\)",html)
    rows=[]; cur=[]
    for v in vals:
        v=re.sub(r'<[^>]+>','',v).strip()
        if v=='' : continue
        cur.append(v)
        # 行尾是发布日期
        if re.match(r'^20\d{2}-\d{2}-\d{2}$',v):
            joined='|'.join(cur)
            if len(cur)>=4 and '发布日期' not in joined and '产品代码' not in joined and '产品名称' not in joined:
                rows.append(cur)
            cur=[]
    return rows
def main(limit=None):
    from urllib.parse import urljoin
    raw=json.loads(http("https://www.bankofchina.com/fimarkets/cs8/lcjz/index_2217.json"))['case']
    idx=[{"url":urljoin("https://www.bankofchina.com/fimarkets/cs8/lcjz/",p['url']),"title":p['title']} for p in raw if p.get('url','').startswith(('http','./','/')) and p.get('url','').endswith(('.html','.htm'))]
    if limit: idx=idx[:limit]
    done=0
    for i,p in enumerate(idx):
        url=p['url']; title=p['title']
        try:
            html=http(url)
            code=re.search(r'产品代码</td>\'\);\s*document\.write\(\'<td[^>]*>([A-Za-z0-9]+)</td>',html)
            code=code.group(1) if code else url.rsplit('_',1)[-1].split('.')[0]
            rows=parse(html)
            json.dump({"title":title,"url":url,"rows":rows},open(os.path.join(OUT,f"{code}.json"),"w",encoding="utf8"),ensure_ascii=False)
            done+=1
            if (i+1)%20==0 or i+1==len(idx): print(f"[{i+1}/{len(idx)}] {code} {title[:20]} rows={len(rows)}",flush=True)
        except Exception as e:
            print(f"[{i+1}] {title[:20]} ERR {e}",flush=True)
        time.sleep(0.5)
    print("DONE",done,"/",len(idx))
if __name__=="__main__":
    main(limit=int(sys.argv[1]) if len(sys.argv)>1 else None)
