"""招行货架完整抓取（并行版）：pageSize 被服务端钳到 10，total≈7689。

思路: 顺序翻页会被限频打断（skill 原 fetch_all() 只拿到 770 条）。
      改为按页号并行请求 + 指数退避重试 + 完整性校验。
用法: python3 fetch_cmb_catalog.py [--out /tmp/cmb_catalog.json] [--workers 8]
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

API = "https://m.cmbchina.com/api/financing/product-list"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}


def fetch_page(page, tries=6):
    last = None
    for i in range(tries):
        try:
            r = requests.get(API, params={"pageIndex": page, "pageSize": 10},
                             timeout=30, headers=UA)
            body = r.json().get("body") or {}
            data = body.get("data")
            if data:
                return data, body.get("total") or 0
            last = "空 body"
        except Exception as e:
            last = str(e)[:80]
        time.sleep(min(1.5 ** i, 12))
    return None, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/tmp/cmb_catalog.json")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    # 先探第一页拿 total
    first, total = fetch_page(1)
    if not first:
        print("第一页拉取失败，放弃", file=sys.stderr)
        return 1
    pages = (total + 9) // 10
    print(f"total={total} -> {pages} 页", flush=True)

    rows = list(first)
    failed = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_page, p): p for p in range(2, pages + 1)}
        done = 0
        for fut in as_completed(futs):
            p = futs[fut]
            data, err = fut.result()
            if data:
                rows += data
            else:
                failed.append((p, err))
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{pages - 1} 页, 已收 {len(rows)} 条", flush=True)

    seen, uniq = set(), []
    for x in rows:
        c = x.get("prdCode")
        if c and c not in seen:
            seen.add(c)
            uniq.append(x)
    json.dump(uniq, open(a.out, "w", encoding="utf8"), ensure_ascii=False)
    print(f"DONE 抓到 {len(uniq)} 只（total={total}），失败页 {len(failed)}，写入 {a.out}", flush=True)
    if failed:
        print(f"失败页样例: {failed[:10]}", file=sys.stderr)
    if total and len(uniq) < total * 0.95:
        print(f"警告：覆盖 {len(uniq)/total:.1%}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
