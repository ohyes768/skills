"""用官网全量缓存给候选补参照：招行货架与官网的产品简称常不同
（招行 "华夏理财悦慧最短持有90天M款C" vs 官网 "华夏理财固收纯债最短持有90天M款C"），
所以不能只比产品名 —— 改用结构化特征（管理人+持有期+期号/款号+份额字母）匹配。

用法: python3 match_refs_struct.py --cand /tmp/cmb_full_refs5.json --out /tmp/cmb_full_refs6.json
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nav_stats as ns  # noqa: E402

# 招行简称 -> 官网正式名 的同义词（实测差异）
SYN = {
    "悦慧": "固收纯债",
    "悦安鑫": "悦安鑫",
    "启元": "启元",
}


def load_official(dirs):
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
            for r in rows:
                d0 = (r.get("netValueDate") or r.get("netvalDt") or
                      r.get("navDate") or r.get("dataDt") or r.get("crtTime"))
                nav = (r.get("shareNetVal") if r.get("shareNetVal") is not None else
                       r.get("nav") if r.get("nav") is not None else
                       r.get("adjustedValue"))
                try:
                    if not d0 or nav is None:
                        continue
                    pts.append((datetime.date.fromisoformat(str(d0)[:10]), float(nav)))
                    sd = (r.get("yieldSevenDate") if r.get("yieldSevenDate") is not None
                          else r.get("sevenDayAnnualized"))
                    if sd is not None:
                        seven.append(float(sd))
                except Exception:
                    pass
            if len(pts) >= 2:
                # 华夏的 rows 是倒序（最新在前），必须排序 —— 否则 ns.stats 抛
                # math domain error（负 span 的幂运算），或算出反向业绩。
                pts.sort(key=lambda x: x[0])
                nm = ""
                if isinstance(data, dict):
                    nm = (data.get("title") or data.get("productName") or "")
                    nm = re.sub(r"\[[^\]]*\]\s*净值报告\s*$", "", nm)
                    nm = re.sub(r"净值报告\s*$", "", nm)
                out[code] = dict(pts=pts, seven=seven, name=nm)
    return out


def calc(pts):
    span = (pts[-1][0] - pts[0][0]).days
    if span <= 0:
        return None
    vals = [v for _, v in pts]
    if max(vals) - min(vals) < 1e-9:
        return None
    try:
        ann, _, sp, mdd = ns.stats(pts)
    except Exception:
        return None
    if ann is None:
        return None
    return dict(span=span, ann=ann, t6=ns.trailing(pts, 6), mdd=mdd, sharpe=sp,
                start=str(pts[0][0]), end=str(pts[-1][0]), n=len(pts))


def feats(name):
    """从产品名抽结构化特征：期号 / 款号 / 持有期天 / 份额字母 / 产品线主干"""
    n = name or ""
    # 清洗官网标题尾巴: "华夏理财现金61号B[24012061B]净值报告"
    n = re.sub(r"\[[^\]]*\]\s*净值报告\s*$", "", n)
    n = re.sub(r"净值报告\s*$", "", n)
    out = {}
    m = re.search(r"(\d+)号", n)
    if m:
        out["hao"] = m.group(1)
    m = re.search(r"([A-Z])款", n)
    if m:
        out["kuan"] = m.group(1)
    m = re.search(r"(\d+)天", n)
    if m:
        out["days"] = m.group(1)
    m = re.search(r"(\d+)期", n)
    if m:
        out["qi"] = m.group(1)
    m = re.search(r"([A-Z])\s*$", n)
    if m:
        out["tail"] = m.group(1)
    # 去掉期号/款号/持有期/份额字母后的"产品线主干"
    stem = re.sub(r"[（(].*?[)）]", "", n)
    stem = re.sub(r"\d+号|\d+期|\d+天|[A-Z]款", " ", stem)
    stem = re.sub(r"\s+", "", stem)
    for s in SYN:
        stem = stem.replace(s, SYN[s])
    # 去掉尾部孤立的大写份额字母（招行"悦安鑫纯债封闭B" vs 官网"悦安鑫纯债封闭（稳盈）"）
    stem = re.sub(r"[A-Z]$", "", stem)
    out["stem"] = stem
    out["stem_tail"] = re.sub(r"[A-Z]$", "", stem)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cand", default="/tmp/cmb_full_refs5.json")
    ap.add_argument("--out", default="/tmp/cmb_full_refs6.json")
    ap.add_argument("--min-days", type=int, default=180)
    a = ap.parse_args()
    rows = json.load(open(a.cand, encoding="utf8"))

    print("读取官网缓存...")
    off = load_official([os.path.join(HERE, "hx"), os.path.join(HERE, "xy")])
    print(f"  华夏+兴银 可用份额: {len(off)}")

    pool = {}
    for code, d in off.items():
        st = calc(d["pts"])
        if st and st["span"] >= a.min_days:
            pool[code] = dict(st, name=d["name"])

    # 结构化特征索引
    idx = {}
    for code, st in pool.items():
        f = feats(st["name"])
        idx.setdefault((f.get("stem"), f.get("hao") or f.get("qi"),
                        f.get("kuan"), f.get("days")), []).append(code)
    print(f"  结构化索引: {len(idx)} 组 | 参照池: {len(pool)}")

    added = 0
    for r in rows:
        if r.get("ref") or (r.get("own") and r["own"]["span"] >= 180):
            continue
        f = feats(r["name"])
        key = (f.get("stem"), f.get("hao") or f.get("qi"), f.get("kuan"), f.get("days"))
        cands = idx.get(key) or []
        if not cands:
            # 放宽：同 stem + 同持有期
            cands = [c for c, st in pool.items()
                     if feats(st["name"]).get("stem") == f.get("stem")
                     and feats(st["name"]).get("days") == f.get("days")]
        if not cands:
            continue
        cands = sorted(cands, key=lambda c: -pool[c]["span"])
        rc = cands[0]
        r["ref"] = dict(pool[rc], code=rc, how="官网同产品线",
                        name=pool[rc]["name"])
        added += 1
    print(f"  新增官网参照: {added}")

    # ---- 七日年化：官网缓存的 yieldSevenDate ----
    # 华夏 yieldSevenDate 是百分数数值(1.2345=1.2345%)，需 /100 归一
    seven_idx = {}
    for code, d in off.items():
        if len(d["seven"]) < 30:
            continue
        vals = [v for v in d["seven"][-90:]]
        vals = [v / 100.0 if v > 1 else v for v in vals]
        seven_idx.setdefault(feats(d["name"]).get("stem"), []).append(
            (code, vals[-1], sum(vals) / len(vals), len(d["seven"])))
    print(f"  七日年化索引(按stem): {len(seven_idx)} 组")

    sd_added = 0
    for r in rows:
        if r.get("cash_metrics") or r.get("seven_day"):
            continue
        f = feats(r["name"])
        stem = f.get("stem")
        cands = seven_idx.get(stem) or []
        if not cands:
            continue
        # 取最新七日年化最高的一支作为同产品线参照
        cands.sort(key=lambda x: -x[1])
        code, latest, avg90, n = cands[0]
        r["seven_day"] = dict(latest=latest, avg90=avg90, n=n,
                              start="", end="")
        r["seven_day_ref"] = f"{code} {off[code]['name'][:26]}"
        sd_added += 1
    print(f"  新增七日年化: {sd_added}")

    json.dump(rows, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    n_ref = sum(1 for r in rows if r.get("ref"))
    n_own = sum(1 for r in rows if r.get("own") and r["own"]["span"] >= 180)
    print(f"候选 {len(rows)} | 自身满期 {n_own} | 有参照 {n_ref}")


if __name__ == "__main__":
    main()
