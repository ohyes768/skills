"""现金管理类业绩：拉同系列老份额的七日年化序列，算近期年化。

用法: python3 cash_series.py <系列关键字> [<系列关键字>...]
输出: 每个系列一行: 成立天数/最新七日年化/近30日均值/近90日均值/极值
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cash_wanli_fetch as C  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms_nav")


def series_for(kw, max_estab=20260101, top=6):
    """找同系列成立最早的 N 支老份额，拉七日年化。

    max_estab: 只取该日期（含）之前成立的份额——即"老份额"，
               2020 年前成立的老产品通常才有长历史七日年化序列。
    """
    prods = C.search_products(kw)
    rows = []
    for p in prods:
        ed = p.get("ESTAB_DATE")
        code = p.get("REAL_PRD_CODE")
        if not ed or not code:
            continue
        try:
            ed_int = int(str(ed))
        except (TypeError, ValueError):
            continue
        if ed_int <= max_estab:
            rows.append((str(ed), code, p.get("PRD_NAME") or ""))
    rows.sort()
    out = []
    for ed, code, name in rows[:top]:
        path = os.path.join(OUT, f"{code}.json")
        if os.path.exists(path):
            data = json.load(open(path, encoding="utf8"))
        else:
            data = {"realPrdCode": code, "name": name, "rows": C.fetch_nav(code)}
            json.dump(data, open(path, "w", encoding="utf8"), ensure_ascii=False)
        out.append((ed, code, name, data["rows"]))
    return out


def summarize(rows):
    sds = []
    for r in rows:
        v = r.get("seven_day")
        if v is None:
            continue
        try:
            sds.append(float(v))
        except (TypeError, ValueError):
            continue  # 接口用 '-' 表示当日无数据
    if not sds:
        return None
    last30 = sds[-30:]
    last90 = sds[-90:]
    return dict(latest=sds[-1], avg30=sum(last30) / len(last30),
                avg90=sum(last90) / len(last90), mn=min(sds), mx=max(sds),
                n=len(sds), start=rows[0]["date"], end=rows[-1]["date"])


if __name__ == "__main__":
    for kw in sys.argv[1:]:
        print(f"\n=== {kw}")
        for ed, code, name, rows in series_for(kw):
            s = summarize(rows)
            if not s:
                print(f"  {code} {name[:36]} 无七日年化数据")
                continue
            print(f"  {code} 成立{ed} {name[:34]:<36} 点{s['n']} {s['start']}~{s['end']} "
                  f"最新{s['latest']:.4%} 均30日{s['avg30']:.4%} 均90日{s['avg90']:.4%} "
                  f"区间[{s['mn']:.4%},{s['mx']:.4%}]")
