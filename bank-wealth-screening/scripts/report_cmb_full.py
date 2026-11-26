"""生成招行 R1/R2、持有期<=180天 的最终筛选报告（Markdown）。

业绩口径：
  本份额     净值型产品自身净值已满 180 天
  同系列参照 自身不足 180 天，取同登记编码 / 同名核心词 的老份额
  七日年化   万份收益型（净值恒 1.0），取官网七日年化率
  同类基准   万份收益型且无直连接口 —— 用已取到同类产品的七日年化区间做参考
  无业绩可参照
"""
import csv
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nav_stats as ns  # noqa: E402

NAV = os.path.join(HERE, "data", "nav_history")


def is_flat(code):
    p = os.path.join(NAV, f"{code}.csv")
    if not os.path.exists(p):
        return False
    rr = list(csv.DictReader(open(p, encoding="utf8")))
    if len(rr) < 2:
        return False
    vals = [float(x["nav"]) for x in rr]
    return max(vals) - min(vals) < 1e-9


def fmt(x):
    return "--" if x is None else f"{x:+.2%}"


def metric_of(r):
    cm = r.get("cash_metrics")
    if cm:
        tot = cm.get("total_year")
        return ("七日年化", cm["seven_day"], tot, None, None, 0,
                f"{cm.get('ref_code')}")
    sd = r.get("seven_day")
    if sd:
        return ("七日年化", sd["latest"], sd["avg90"], None, None, sd["n"],
                r.get("seven_day_ref", ""))
    o, rf = r.get("own"), r.get("ref")
    if o and o["span"] >= 180:
        return ("本份额", o["t6"], o["ann"], o["mdd"], o["sharpe"], o["span"], "本份额")
    if rf:
        return ("同系列参照", rf["t6"], rf["ann"], rf["mdd"], rf["sharpe"], rf["span"],
                rf.get("name") or rf.get("code", ""))
    if is_flat(r["code"]):
        return ("同类基准", None, None, None, None, 0, "")
    return (None, None, None, None, None, 0, None)


def main():
    rows = json.load(open("/tmp/cmb_full_refs5.json", encoding="utf8"))
    for r in rows:
        (r["m_kind"], r["m_t6"], r["m_ann"], r["m_mdd"], r["m_sr"], r["m_span"],
         r["m_ref"]) = metric_of(r)

    # 已取到的七日年化样本 -> 同类基准区间
    cash7 = [r["m_t6"] for r in rows if r["m_kind"] == "七日年化" and r["m_t6"]]
    lo, hi = (min(cash7), max(cash7)) if cash7 else (None, None)
    avg = sum(cash7) / len(cash7) if cash7 else None

    reco = []
    for r in rows:
        if r["m_kind"] != "本份额":
            continue
        if r["m_t6"] is None or r["m_t6"] <= 0 or r["m_mdd"] < -0.005:
            continue
        if "美元" in r["name"]:
            continue
        reco.append((r["m_t6"] * 100 - abs(r["m_mdd"]) * 300, r))
    reco.sort(key=lambda x: -x[0])

    L = []
    A = L.append
    A("# 招商银行 R1/R2 理财筛选 · 持有期 ≤180 天")
    A("")
    A(f"净值数据截至 **2026-11-25**｜货架快照 **2026-11-26**｜"
      f"招行全目录 **7687/7689** 只 → 符合筛选 **{len(rows)}** 只")
    A("")
    A("**筛选条件**：风险等级 R1/R2 · 持有期 ≤180 天 · 起购 <20 万 · "
      "排除大额存单/私行/私募/定向/机构专享")
    A("")
    A("**业绩口径**")
    A("")
    A("| 口径 | 数量 | 说明 |")
    A("|---|---|---|")
    for kind, desc in [("本份额", "该份额净值已满 180 天，直接用其净值序列"),
                       ("同系列参照", "自身不足 180 天，取同登记编码/同系列老份额"),
                       ("七日年化", "万份收益型（净值恒 1.0），官网七日年化率"),
                       ("同类基准", "万份收益型且无直连接口，参考同类产品七日年化区间"),
                       (None, "以上均无法覆盖")]:
        n = sum(1 for r in rows if r["m_kind"] == kind)
        A(f"| {kind or '无业绩可参照'} | {n} | {desc} |")
    A("")
    A(f"> **同类基准参考**：已取到 **{len(cash7)}** 只万份收益型产品的七日年化，"
      f"区间 **{fmt(lo)} ~ {fmt(hi)}**，均值 **{fmt(avg)}**。"
      f"货币型现金管理类产品收益高度同质，落在该区间即属正常。")
    A("")
    A("---")
    A("")
    A("## 🏆 推荐 3 只")
    A("")
    for i, (s, r) in enumerate(reco[:3], 1):
        A(f"### {i}. {r['name']}")
        A("")
        A(f"`{r['code']} · {r['risk']} · 持有 {r['hold']} 天 · {r['mgr']} · {r['style']}`")
        A("")
        A(f"近6月年化 **{fmt(r['m_t6'])}**｜成立年化 **{fmt(r['m_ann'])}**｜"
          f"最大回撤 **{fmt(r['m_mdd'])}**｜Sharpe **{r['m_sr']:.2f}**")
        A(f"本份额成立 {r['m_span']} 天")
        A("")
    A("**备选（更短锁定）**")
    A("")
    for s, r in [x for x in reco if x[1]["hold"] <= 30][:3]:
        A(f"- `{r['code']}` {r['name']} · 持有{r['hold']}天 · 近6月 {fmt(r['m_t6'])} · "
          f"成立 {fmt(r['m_ann'])} · 回撤 {fmt(r['m_mdd'])} · Sharpe {r['m_sr']:.2f}")
    A("")
    A("---")
    A("")
    A("## 全量候选")
    A("")
    for h in sorted({r["hold"] for r in rows}):
        lst = [r for r in rows if r["hold"] == h]
        A(f"### 持有 {h} 天（{len(lst)} 只）")
        A("")
        A("| 风险 | 代码 | 管理人 | 名称 | 口径 | 参照 | 成立天数 | 近6月年化 | 成立年化 | 最大回撤 | Sharpe |")
        A("|---|---|---|---|---|---|---|---|---|---|---|")
        lst.sort(key=lambda r: -(r["m_ann"] if r["m_ann"] is not None else -9))
        for r in lst:
            sr = f"{r['m_sr']:.2f}" if r["m_sr"] is not None else "--"
            ref = (r["m_ref"] or "")[:28]
            if r["m_kind"] == "同类基准":
                A(f"| {r['risk']} | `{r['code']}` | {r['mgr']} | {r['name']} | "
                  f"同类基准 | 参考区间 {fmt(lo)}~{fmt(hi)} | -- | -- | -- | -- | -- |")
            elif r["m_kind"]:
                A(f"| {r['risk']} | `{r['code']}` | {r['mgr']} | {r['name']} | "
                  f"{r['m_kind']} | {ref} | {r['m_span']}d | {fmt(r['m_t6'])} | "
                  f"{fmt(r['m_ann'])} | {fmt(r['m_mdd'])} | {sr} |")
            else:
                A(f"| {r['risk']} | `{r['code']}` | {r['mgr']} | {r['name']} | "
                  f"无业绩可参照 | -- | -- | -- | -- | -- | -- |")
        A("")
    A("---")
    A("")
    A("## ⚠️ 需注意")
    A("")
    A("### 美元产品（净值涨幅为人民币计价，未含汇兑）")
    A("")
    for r in rows:
        if "美元" in r["name"] and r["m_kind"] == "本份额":
            A(f"- `{r['code']}` {r['name']} · 持有{r['hold']}天 · "
              f"近6月 {fmt(r['m_t6'])} · 成立 {fmt(r['m_ann'])}")
    A("")
    A("### 近6月实际亏损（净值型，万份收益型已排除）")
    A("")
    negs = [r for r in rows if r["m_kind"] == "本份额" and r["m_t6"] is not None
            and r["m_t6"] <= 0 and not is_flat(r["code"])]
    if not negs:
        A("（无）")
    for r in negs:
        A(f"- `{r['code']}` {r['name']} · {r['mgr']} · 持有{r['hold']}天 · "
          f"近6月 {fmt(r['m_t6'])} · 成立 {fmt(r['m_ann'])} · 回撤 {fmt(r['m_mdd'])}")
    A("")
    A("仅供参考，不构成投资建议。")
    A("")
    open("/tmp/cmb_report.md", "w", encoding="utf8").write("\n".join(L))
    print(f"报告写入 /tmp/cmb_report.md（{len(L)} 行）")

    import collections
    print("\n=== 口径分布")
    print(" ", dict(collections.Counter(r["m_kind"] or "无业绩可参照" for r in rows)))
    print(f"\n=== 同类基准区间: {fmt(lo)} ~ {fmt(hi)} 均值 {fmt(avg)} (n={len(cash7)})")
    print("\n=== 推荐 TOP 8")
    for s, r in reco[:8]:
        print(f"  {r['risk']} {r['code']:<10} {r['mgr']:<5} h={r['hold']:<4} "
              f"span={r['m_span']:>4}d 近6M{r['m_t6']:+.2%} 成立{r['m_ann']:+.2%} "
              f"回撤{r['m_mdd']:+.2%} SR{r['m_sr']:.2f}  {r['name'][:34]}")
    print("\n=== 亏损产品")
    for r in negs[:10]:
        print(f"  {r['code']:<10} {r['mgr']:<5} 近6M{r['m_t6']:+.2%} 成立{r['m_ann']:+.2%} "
              f"回撤{r['m_mdd']:+.2%} {r['name'][:36]}")


if __name__ == "__main__":
    main()
