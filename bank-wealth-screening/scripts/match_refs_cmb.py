"""同系列参照匹配：候选 -> 最可信的老份额。

匹配规则（严格）：
  1. 参照份额与候选必须是**同一登记编码(regCode)**下的不同份额，
     或产品名核心词完全一致。
  2. 参照成立天数 >= 180（不足 180 视为不可信）。
  3. 多个参照取成立最久的一个。
  4. 跨登记编码的（系列名相同但 regCode 不同）标为"跨编码-仅参考"。
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nav_stats as ns  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAV = os.path.join(HERE, "data", "nav_history")


def load_pts(code):
    p = os.path.join(NAV, f"{code}.csv")
    if not os.path.exists(p):
        return None
    rows = list(csv.DictReader(open(p, encoding="utf8")))
    if len(rows) < 2:
        return None
    return [(datetime.date.fromisoformat(r["date"]), float(r["nav"])) for r in rows]


def calc(code):
    pts = load_pts(code)
    if not pts:
        return None
    span = (pts[-1][0] - pts[0][0]).days
    vals = [v for _, v in pts]
    flat = max(vals) - min(vals) < 1e-9
    ann, _, sp, mdd = ns.stats(pts)
    return dict(span=span, ann=ann, t6=ns.trailing(pts, 6), mdd=mdd, sharpe=sp,
                flat=flat, start=str(pts[0][0]), end=str(pts[-1][0]), n=len(pts))


def core_words(name):
    """产品名 -> 系列核心词集合（用于粗匹配）。"""
    s = re.sub(r"[（(].*?[)）]", " ", name or "")
    s = re.sub(r"第?\d+期", " ", s)
    s = re.sub(r"\d+号", " ", s)
    s = re.sub(r"\d+天", " ", s)
    s = re.sub(r"[A-Z]\b", " ", s)
    s = re.sub(r"(人民币|理财计划|理财产品|固定收益类|固收类|增强型|开放式|封闭式|"
               r"现金管理类|混合类|权益类|纯债|净值型|定期开放|日开|最短持有期|最低持有期)",
               " ", s)
    return {w for w in re.split(r"[\s]+", s) if len(w) >= 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_cand.json")
    ap.add_argument("--catalog", default="/tmp/cmb_catalog.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs.json")
    ap.add_argument("--min-days", type=int, default=180)
    a = ap.parse_args()

    cand = json.load(open(a.cand, encoding="utf8"))
    catalog = {p["prdCode"]: p for p in json.load(open(a.catalog, encoding="utf8"))}

    # 参照池：所有已缓存净值、成立 >= min_days 的份额
    pool = {}
    for f in glob.glob(os.path.join(NAV, "*.csv")):
        code = os.path.basename(f)[:-4]
        st = calc(code)
        if st and st["span"] >= a.min_days and not st["flat"]:
            pool[code] = st

    # 参照池按登记编码索引
    reg_index = {}
    name_index = {}
    for code in pool:
        p = catalog.get(code)
        if not p:
            continue
        reg = p.get("regCode") or ""
        if reg:
            reg_index.setdefault(reg, []).append(code)
        cw = core_words(p.get("prdBrief") or "")
        if cw:
            name_index.setdefault(frozenset(cw), []).append(code)

    out = []
    for c in cand:
        code = c["code"]
        p = catalog.get(code, {})
        reg = c.get("reg") or p.get("regCode") or ""
        cw = core_words(c["name"])
        own = calc(code)

        # 优先级 1: 同登记编码的其他份额
        cands = []
        for rc in reg_index.get(reg, []):
            if rc == code:
                continue
            cands.append((pool[rc]["span"], rc, "同登记编码"))
        # 优先级 2: 产品名核心词完全一致
        if not cands:
            for rc in name_index.get(frozenset(cw), []):
                if rc == code:
                    continue
                cands.append((pool[rc]["span"], rc, "同名核心词"))
        cands.sort(reverse=True)
        ref = None
        if cands:
            span, rc, how = cands[0]
            ref = dict(pool[rc], code=rc, how=how,
                       name=(catalog.get(rc, {}).get("prdBrief") or rc))
        c["own"] = own
        c["ref"] = ref
        c["ref_pool_size"] = len(cands)
        out.append(c)

    json.dump(out, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    n_ref = sum(1 for c in out if c["ref"])
    n_own_ok = sum(1 for c in out if c["own"] and c["own"]["span"] >= 180)
    print(f"候选 {len(out)}")
    print(f"  自身净值成立>=180d: {n_own_ok}")
    print(f"  有同系列参照: {n_ref}")
    print(f"  无参照（需标注'无业绩可参照'）: {len(out) - n_ref}")
    print(f"写入 {a.out}")


if __name__ == "__main__":
    main()
