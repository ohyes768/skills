#!/usr/bin/env python3
"""同系列老份额参照查找器。

用法:
  python3 series_ref.py <系列关键字> [--top 5] [--min-days N]

在各通道本地产品索引（citic/hx/ny products json + 招行目录缓存；目录可用环境变量 BWS_NAV_DIR 覆盖）
里按系列名关键字找同系列份额，优先选成立最早、且本地有净值数据的份额，
输出 nav_stats 同款业绩表 —— 用于给新份额找"系列业绩参照"。

参照判定规则（与 SKILL.md 一致）：同系列必须同产品线（名称逐字前缀匹配，
同家族不同产品线不算），成立 ≥1 年的份额才可信。
"""
import argparse
import datetime
import json
import os
import sys

import nav_stats as ns

STUDY = os.environ.get("BWS_NAV_DIR", os.path.expanduser("~/study/nav"))


def candidates(keyword, online_cmb=False):
    """-> [(code, name, source)] 名称含关键字的候选份额。"""
    out = []
    # 信银
    f = os.path.join(STUDY, "citic_products.json")
    if os.path.exists(f):
        for p in json.load(open(f)):
            if keyword in (p.get("prodName") or ""):
                out.append((p["prodCode"], p.get("prodName") or "", "citic"))
    # 华夏
    f = os.path.join(STUDY, "hx_products.json")
    if os.path.exists(f):
        for p in json.load(open(f)):
            if keyword in (p.get("sprd_name") or ""):
                out.append((p["sprd_code"], p.get("sprd_name") or "", "hx"))
    # 南银
    f = os.path.join(STUDY, "ny_products.json")
    if os.path.exists(f):
        for p in json.load(open(f)):
            if keyword in (p.get("name") or ""):
                out.append((p.get("salesCode") or "", p.get("name") or "", "ny"))
    # 招行目录（可选在线）
    if online_cmb:
        try:
            import on_sale_cmb
            for p in on_sale_cmb.fetch_all():
                nm = p.get("prdName") or ""
                if keyword in nm:
                    out.append((p["prdCode"], nm, "cmb"))
        except Exception as e:
            print(f"招行目录拉取失败: {e}", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keyword", help="系列名关键字，如 慧盈象固收增强 / 悦嘉最短持有180天")
    ap.add_argument("--top", type=int, default=5, help="输出最老的 N 支有数据份额")
    ap.add_argument("--min-days", type=int, default=180,
                    help="参照份额最低成立天数（默认 180，1 年以上才算勉强可信）")
    ap.add_argument("--online-cmb", action="store_true", help="同时搜招行目录（在线）")
    a = ap.parse_args()

    cands = candidates(a.keyword, a.online_cmb)
    print(f"候选 {len(cands)} 支，逐个查净值（有本地数据才输出）...\n", file=sys.stderr)
    scored = []
    for code, name, src in cands:
        code = code.upper()
        try:
            pts = ns.load(code)
        except Exception:
            if src != "cmb":
                continue
            # 招行销售代码在线拉一次
            import subprocess
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__),
                            "fetch_nav_history.py"), "--out", ns.NAV_DIR, code],
                           check=False, capture_output=True)
            try:
                pts = ns.load(code)
            except Exception:
                continue
        if not pts or len(pts) < 2:
            continue
        span = (pts[-1][0] - pts[0][0]).days
        if span < a.min_days:
            continue
        scored.append((span, code, name, src, pts))
    scored.sort(reverse=True)
    if not scored:
        print(f"系列「{a.keyword}」没有成立 ≥{a.min_days} 天且本地有净值的份额——该系列无业绩可参照")
        return
    print(f"{'产品':<34}{'代码':<14}{'来源':<6}{'成立时长':>9}{'近6月年化':>10}{'成立年化':>10}"
          f"{'最大回撤':>10}{'成立Sharpe':>12}")
    for span, code, name, src, pts in scored[:a.top]:
        try:
            ann, _, sp, mdd = ns.stats(pts)
            t6 = ns.trailing(pts, 6)
        except Exception:
            continue
        dur = f"{span//365}年{span%365}天" if span >= 365 else f"{span}天"
        nm = name[:32]
        print(f"{nm:<34}{code:<14}{src:<6}{dur:>9}{ns.fmt(t6):>10}{ns.fmt(ann):>10}"
              f"{ns.fmt(mdd):>10}{ns.fmt(sp, pct=False):>12}")
    newest = scored[-1]
    print(f"\n注：参照份额业绩不代表新份额，仅证明该产品线策略经得起检验；"
          f"数据截至 {newest[4][-1][0]}。")


if __name__ == "__main__":
    main()
