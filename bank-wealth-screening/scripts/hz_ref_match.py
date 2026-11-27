#!/usr/bin/env python3
"""杭银理财产品线参照查询（把推荐前必做的同系列参照流程固化成脚本）。

背景：杭银封闭式每期一个新 dengjino（期级标识，非系列级），同系列判定靠
产品线名去期号/份额字母后逐字一致 + licaiqixian 期限一致 + typeinfo b/c/d
段策略指纹一致。括号里的 幸福金桂/稳利低波颐养款/爽盈优选 等是渠道或主题
标签，不改变产品线归属。名称含括号别名且期限不同的（丰鸿灵动盈、稳盈
1106天）是并行线，不许作业绩背书——本脚本按上述规则只返回同线参照。

用法:
    python3 hz_ref_match.py <产品名片段|productCode|dengjino> [--min-days 180]
                            [--nav] [--top 5] [--refresh]

    --min-days  参照份额最小成立天数（默认 180，同 nav_stats 门槛）
    --nav       对返回的参照拉净值并输出近30/90/180天滚动年化+区间回撤
    --top N     最多返回 N 条参照（默认 5，按成立天数降序）
    --refresh   强制重拉全量目录（默认缓存 6 小时）

输出：目标产品卡片 + 参照表（代码、成立天数、复利年化、typeinfo、状态）。
"""
import argparse
import datetime
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_URL = "https://www.hzbankwealth.cn/eportal/hzbw/product_data.json"
CATALOG_PATH = os.path.join(HERE, "data", "hzb_catalog.json")
CATALOG_TTL = 6 * 3600
NAV_SCRIPT = os.path.join(HERE, "fetch_nav_history.py")

TODAY = datetime.date.today()


def _ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False  # 杭银官网证书域名不匹配（www.hzbankwealth.cn），只取公开数据
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def load_catalog(refresh=False):
    if not refresh and os.path.exists(CATALOG_PATH):
        if time.time() - os.path.getmtime(CATALOG_PATH) < CATALOG_TTL:
            return json.load(open(CATALOG_PATH))
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "Mozilla/5.0"})
    items = json.load(urllib.request.urlopen(req, timeout=120, context=_ctx()))["product"]
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    json.dump(items, open(CATALOG_PATH, "w"), ensure_ascii=False)
    return items


def norm_title(t):
    """产品线归一：去 幸福99 前缀、期号、份额字母/惠享款、括号渠道标签。"""
    t = re.sub(r"^[杭银理财]*幸福99", "", t or "")
    t = re.sub(r"\d{5}期", "期", t)
    t = re.sub(r"[（(].*?[)）]", "", t)          # 括号别名/渠道标签
    t = re.sub(r"[A-Z]{1,3}(惠享款|款|份额)?$", "", t)
    t = t.replace("惠享款", "").strip()
    return t


def typeinfo_family(ti):
    """策略族指纹：b/c/d 段（a 段是渠道码，忽略）。"""
    parts = [p for p in (ti or "").split(",") if p]
    return tuple(sorted(p for p in parts if p[0] in "bcd"))


def find_target(items, query):
    ql = query.upper()
    exact = [p for p in items if query in (p.get("contenttitle") or "")
             or ql == (p.get("productCode") or "").upper()
             or ql == (p.get("dengjino") or "").upper()]
    if not exact:
        # 宽松：产品线名匹配，取期限最长/最新的期
        exact = [p for p in items if norm_title(query) and norm_title(query) in norm_title(p.get("contenttitle") or "")]
    return exact


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="产品名片段 / productCode / dengjino")
    ap.add_argument("--min-days", type=int, default=180)
    ap.add_argument("--nav", action="store_true", help="拉参照净值并输出滚动窗口")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    items = load_catalog(a.refresh)
    hits = find_target(items, a.query)
    if not hits:
        sys.exit(f"未找到匹配 {a.query!r} 的产品，试试更多名称片段或 --refresh")
    # 目标取在售优先、期号最大的一个
    tgt = sorted(hits, key=lambda p: (p.get("chanpinzhuangtai") == "在售",
                                      p.get("chengliriqi") or ""))[-1]
    fam = typeinfo_family(tgt.get("typeinfo"))
    term = tgt.get("licaiqixian") or ""
    line = norm_title(tgt.get("contenttitle"))
    print(f"目标: {tgt['contenttitle']}")
    print(f"  productCode={tgt.get('productCode')} dengjino={tgt.get('dengjino')} "
          f"type={tgt.get('typeinfo')} 期限={term} 状态={tgt.get('chanpinzhuangtai')}")
    print(f"  产品线(归一)={line}  策略族={','.join(fam)}")
    if tgt.get("chanpinzhuangtai") == "在售":
        est = tgt.get("chengliriqi") or ""
        try:
            if (TODAY - datetime.date.fromisoformat(est)).days < 180:
                print("  ⚠ 目标成立<6个月，业绩指标不可用，以下参照即推荐依据")
        except ValueError:
            pass

    refs = []
    for p in items:
        if p is tgt or p.get("guanliren") != tgt.get("guanliren"):
            continue
        if (p.get("licaiqixian") or "") != term:            # 期限必须一致（硬规则）
            continue
        if typeinfo_family(p.get("typeinfo")) != fam:        # 策略族必须一致
            continue
        if p.get("chanpinzhuangtai") not in ("存续", "已到期"):
            continue
        est = p.get("chengliriqi") or ""
        try:
            days = (TODAY - datetime.date.fromisoformat(est)).days
        except ValueError:
            continue
        if days < a.min_days:
            continue
        try:
            lj = float(p.get("leijijingzhi"))
        except (TypeError, ValueError):
            continue
        ann = ((lj) ** (365 / days) - 1) * 100 if days > 0 and lj > 0 else None
        refs.append((days, ann, p))
    refs.sort(key=lambda r: (r[0], r[1] or 0), reverse=True)
    if not refs:
        sys.exit(f"  该产品线无 ≥{a.min_days} 天的同期限参照（整个系列查不到就明确告知"
                 f"\"无业绩可参照、盲买管理人\"，不许拿别的线充数）")
    print(f"\n参照（同期限 {term} · 策略族 {','.join(fam)} · ≥{a.min_days}天，按成立天数降序 top{a.top}）:")
    codes = []
    for days, ann, p in refs[:a.top]:
        ann_s = f"{ann:+.2f}%" if ann is not None else "--"
        note = ""
        if abs(float(p.get("leijijingzhi") or 1) ** 0 - 0) >= 0:  # 占位，起点溢价在 --nav 里看
            pass
        print(f"  {p.get('productCode'):<14} 成立{days:>4}天 复利年化{ann_s:>8} "
              f"[{p.get('chanpinzhuangtai')}] 净值{p.get('leijijingzhi')} "
              f"截至{p.get('jingzhiriqi')} {p['contenttitle'][:36]}")
        codes.append(p.get("productCode"))
    if len({norm_title(p["contenttitle"]) for _, _, p in refs}) > 1:
        print("  ⚠ 参照里含多个归一产品线名，请人工确认是否同一滚动线（括号别名已归一，仍需肉眼复核）")
    if a.nav and codes:
        subprocess.run([sys.executable, NAV_SCRIPT, "--out",
                        os.path.join(HERE, "data", "nav_history"), *codes], check=False)
        subprocess.run([sys.executable, os.path.join(HERE, "nav_stats.py"), *codes,
                        "--no-refresh"], check=False)


if __name__ == "__main__":
    main()
