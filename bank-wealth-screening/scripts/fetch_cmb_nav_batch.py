"""并行批量拉招行候选产品净值（cfweb getSAValueByPage）。

用法: python3 fetch_cmb_nav_batch.py --codes-file codes.txt [--out data/nav_history]
"""
import argparse
import csv
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_nav_history import fetch_cmb  # noqa: E402

_lock = threading.Lock()


def fetch(code, out_dir, tries=3):
    last = ""
    for _ in range(tries):
        try:
            rows = fetch_cmb(code)
        except Exception as e:
            last = f"FAIL {str(e)[:40]}"
            continue
        if not rows:
            last = "0点"
            continue
        path = os.path.join(out_dir, f"{code}.csv")
        tmp = path + f".tmp{threading.get_ident()}"
        with open(tmp, "w", newline="", encoding="utf8") as f:
            w = csv.writer(f)
            w.writerow(["date", "nav"])
            w.writerows(rows)
        os.replace(tmp, path)
        return code, len(rows), f"{rows[0][0]}->{rows[-1][0]}"
    return code, 0, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes-file", required=True)
    ap.add_argument("--out", default="data/nav_history")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    codes = [c.strip().upper() for c in open(a.codes_file) if c.strip()]
    os.makedirs(a.out, exist_ok=True)
    ok, fail, done = 0, [], 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch, c, a.out): c for c in codes}
        for fut in as_completed(futs):
            code, n, msg = fut.result()
            done += 1
            if n > 0:
                ok += 1
            else:
                fail.append((code, msg))
            if done % 100 == 0 or done == len(codes):
                print(f"  {done}/{len(codes)} 有数据 {ok}", flush=True)
    print(f"DONE 有数据 {ok}/{len(codes)}")
    if fail:
        print("失败样例:", fail[:25])


if __name__ == "__main__":
    main()
