"""用各管理人官网全量缓存(hx/xy/citic/)给全量候选补同系列参照业绩。

参照池 = 官网缓存里所有有足够历史深度的份额，按 (产品名核心词) 索引。
匹配规则：
  1. 优先"同登记编码"（招行目录里可见）
  2. 次选"同名核心词完全一致"
  3. 参照须 span >= min_days
用法: python3 match_refs_official.py --cand /tmp/cmb_full_refs5.json --out /tmp/cmb_full_refs6.json
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nav_stats as ns  # noqa: E402

NAV = os.path.join(HERE, "data", "nav_history")


def load_official(dirs):
    """读取官网缓存 json -> {code: (pts, meta)}，pts = [(date, nav)]"""
    out = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "*.json")):
            try:
                data = json.load(open(f, encoding="utf8"))
            except Exception:
                continue
            code = os.path.basename(f)[:-5]
            rows = data.get("rows") if isinstance(data, dict) else data
            if not rows or len(rows) < 2:
                continue
            pts, seven = [], []
            ok = True
            for r in rows:
                # 各家日期/净值字段名不同
                d0 = (r.get("date") or r.get("netValueDate") or r.get("netvalDt")
                      or r.get("navDate") or r.get("dataDt") or r.get("crtTime"))
                nav = (r.get("nav") if r.get("nav") is not None else
                       r.get("shareNetVal") if r.get("shareNetVal") is not None else
                       r.get("adjustedValue") if r.get("adjustedValue") is not None else
                       r.get("unitNetValue"))
                try:
                    if not d0 or nav is None:
                        continue
                    d0 = str(d0)[:10]
                    pts.append((datetime.date.fromisoformat(d0), float(nav)))
                    sd = r.get("yieldSevenDate") or r.get("sevenDayAnnualized")
                    if sd is not None:
                        seven.append(float(sd))
                except Exception:
                    ok = False
                    break
            if ok and len(pts) >= 2:
                out[code] = (pts, seven, data)
    return out


def calc(pts):
    span = (pts[-1][0] - pts[0][0]).days
    if span <= 0:
        return None
    vals = [v for _, v in pts]
    flat = max(vals) - min(vals) < 1e-9
    try:
        ann, _, sp, mdd = ns.stats(pts)
    except Exception:
        return None
    if ann is None:
        return None
    return dict(span=span, ann=ann, t6=ns.trailing(pts, 6), mdd=mdd, sharpe=sp,
                flat=flat, start=str(pts[0][0]), end=str(pts[-1][0]), n=len(pts))


def core_words(name):
    s = re.sub(r"[（(].*?[)）]", " ", name or "")
    s = re.sub(r"第?\d+期", " ", s)
    s = re.sub(r"\d+号", " ", s)
    s = re.sub(r"\d+天", " ", s)
    s = re.sub(r"[A-Z]\b", " ", s)
    s = re.sub(r"(人民币|理财计划|理财产品|固定收益类|固收类|增强型|开放式|封闭式|"
               r"现金管理类|混合类|权益类|纯债|净值型|定期开放|日开|最短持有期|最低持有期|"
               r"现金管理型|型)", " ", s)
    return frozenset(w for w in re.split(r"\s+", s) if len(w) >= 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs5.json")
    ap.add_argument("--catalog", default="/tmp/cmb_catalog.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs6.json")
    ap.add_argument("--min-days", type=int, default=180)
    a = ap.parse_args()

    rows = json.load(open(a.cand, encoding="utf8"))
    catalog = {p["prdCode"]: p for p in json.load(open(a.catalog, encoding="utf8"))}

    print("读取官网缓存...")
    off = load_official([os.path.join(HERE, "hx"), os.path.join(HERE, "xy"),
                          os.path.join(HERE, "citic")])
    print(f"  官网缓存可用份额: {len(off)}")

    # 参照池：span >= min_days 且非万份收益型
    pool = {}
    for code, (pts, seven, meta) in off.items():
        st = calc(pts)
        if st and st["span"] >= a.min_days and not st["flat"]:
            pool[code] = st
    print(f"  可作参照(span>={a.min_days}d, 非万份收益型): {len(pool)}")

    # 七日年化池：官网缓存里带 yieldSevenDate / sevenDayAnnualized 的份额
    seven_pool = {}
    for code, (pts, seven, meta) in off.items():
        if len(seven) < 30:
            continue
        vals = [v for v in seven[-90:]]
        # 华夏 yieldSevenDate 是百分数数值(1.2345=1.2345%)，信银 sevenDaysIncomeRate 是小数
        vals = [v / 100.0 if v > 1 else v for v in vals]
        seven_pool[code] = dict(latest=vals[-1],
                                avg90=sum(vals) / len(vals),
                                n=len(seven))
    print(f"  七日年化池: {len(seven_pool)}")

    # 按核心词索引（官网缓存自带产品名字段，不必经招行目录中转）
    name_index = {}
    for code, (pts, seven, meta) in off.items():
        nm = ""
        if isinstance(meta, dict):
            nm = (meta.get("title") or meta.get("productName") or
                  meta.get("productFullName") or "")
        if not nm:
            continue
        # 华夏/兴银的标题带尾部噪声: "[code]净值报告"
        nm = re.sub(r"\[[^\]]*\]\s*净值报告\s*$", "", nm)
        nm = re.sub(r"净值报告\s*$", "", nm)
        cw = core_words(nm)
        if cw:
            name_index.setdefault(cw, []).append(code)
    print(f"  官网核心词索引: {len(name_index)} 组")

    added = 0
    for r in rows:
        if r.get("ref"):
            continue                      # 已有参照
        if r.get("own") and r["own"]["span"] >= 180:
            continue                      # 自身已可用
        cw = core_words(r["name"])
        cands = name_index.get(cw, [])
        if not cands:
            # 放宽：取核心词集合是候选核心词子集的最长匹配
            best, best_len = None, 0
            for cw2, lst2 in name_index.items():
                if cw2 and cw2 <= cw and len(cw2) > best_len:
                    best, best_len = lst2, len(cw2)
            cands = best or []
        cands = [c for c in cands if c in pool] or cands
        if not cands:
            continue
        cands = sorted(cands, key=lambda c: -pool[c]["span"] if c in pool else 0)
        rc = cands[0]
        if rc not in pool:
            continue
        r["ref"] = dict(pool[rc], code=rc, how="官网同名核心词",
                        name=(catalog.get(rc, {}).get("prdBrief") or rc))
        added += 1
    print(f"  新增官网参照: {added}")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    n_ref = sum(1 for r in rows if r.get("ref"))
    n_own = sum(1 for r in rows if r.get("own") and r["own"]["span"] >= 180)
    print(f"候选 {len(rows)} | 自身满期 {n_own} | 有参照 {n_ref} | "
          f"无业绩可参照 {len(rows) - n_own - n_ref}")
    print(f"写入 {a.out}")


if __name__ == "__main__":
    main()
