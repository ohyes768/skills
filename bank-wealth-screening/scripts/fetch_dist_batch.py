"""批量拉代销产品净值：按产品名在各管理人官网搜索 -> 拉历史净值 -> 缓存。

用法: python3 fetch_dist_batch.py <json文件>
json: [{"code":"GD100010","name":"产品全名","mgr":"光大"}, ...]
输出: scripts/<dir>/<key>.json  (格式兼容 nav_stats._load_json)
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fetch_dist_nav as F  # noqa: E402

OUT_DIRS = {"光大": "ceb", "兴银": "xy", "信银": "citic", "民生": "ms_nav",
            "华夏": "hx", "南银": "ny", "中银": "boc"}


def save(mgr, key, payload):
    d = OUT_DIRS.get(mgr, "dist")
    os.makedirs(os.path.join(HERE, d), exist_ok=True)
    path = os.path.join(HERE, d, f"{key}.json")
    json.dump(payload, open(path, "w", encoding="utf8"), ensure_ascii=False)
    return path


def run_one(item):
    mgr, name, code = item["mgr"], item["name"], item["code"]
    base = item.get("search") or name  # 去掉份额字母便于搜
    try:
        if mgr == "光大":
            hits = F.ceb_search(base)
            if not hits:
                return {"code": code, "status": "no_match"}
            cp, nm = hits[0]
            rows = F.ceb_hist(cp)
            save(mgr, cp, {"cpCode": cp, "name": nm, "rows": rows})
            return {"code": code, "status": "ok", "key": cp, "rows": len(rows)}
        if mgr == "兴银":
            hits = F.xy_search(base)
            if not hits:
                return {"code": code, "status": "no_match"}
            h = hits[0]
            pc = h["productCode"]
            rows = F.xy_nav(pc)
            save(mgr, pc, {"productCode": pc, "productName": h.get("productName"),
                           "riskLevel": h.get("riskLevel"), "rows": rows})
            return {"code": code, "status": "ok", "key": pc, "rows": len(rows)}
        if mgr == "民生":
            hits = F.ms_search(base)
            if not hits:
                return {"code": code, "status": "no_match"}
            rc = hits[0]["REAL_PRD_CODE"]
            rows = F.ms_nav(rc)
            save(mgr, rc, {"realPrdCode": rc, "name": hits[0].get("PRD_NAME"), "rows": rows})
            return {"code": code, "status": "ok", "key": rc, "rows": len(rows)}
        if mgr == "信银":
            hits = F.citic_search(base)
            if not hits:
                return {"code": code, "status": "no_match"}
            h = hits[0]
            pc = h.get("fundCode") or h.get("prodCode")
            data = F.citic_nav(pc)
            rows = data.get("productNavList") or []
            save(mgr, pc, {"prodCode": pc, "name": h.get("fundName"), "rows": rows})
            return {"code": code, "status": "ok", "key": pc, "rows": len(rows)}
        if mgr == "华夏":
            hits = F.hx_search(base)
            if not hits:
                return {"code": code, "status": "no_match"}
            pid, title, addr = hits[0]
            rows = F.hx_nav(pid, [a for _, _, a in hits])
            save(mgr, pid, {"productId": pid, "title": title, "rows": rows})
            return {"code": code, "status": "ok", "key": pid, "rows": len(rows)}
        return {"code": code, "status": "no_fetcher"}
    except Exception as e:
        return {"code": code, "status": "err", "err": str(e)[:120]}


if __name__ == "__main__":
    import re
    items = json.load(open(sys.argv[1], encoding="utf8"))
    for it in items:
        r = run_one(it)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        time.sleep(0.5)
