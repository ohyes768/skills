"""个人持仓速览（合并产品指标）。

用法:
    python portfolio.py [--no-refresh]

持仓配置在 data/holdings.json: {产品代码: {shares, principal, buy_date}}。
自动拉取(默认)最新净值，按**近3月年化**从高到低排序（近期动量优先，避免
老产品凭长持有期年化占先），以要点形式逐只输出：
持有信息（总收益率、持有年化、近1月/近3月年化）+ 产品指标（风险等级、
成立时长、近6月年化、成立年化、最大回撤、成立/近1年Sharpe）。
不显示本金、市值与收益金额。
"""
import argparse
import csv
import datetime
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

from code_convert import convert

RF = 0.015
HERE = os.path.dirname(os.path.abspath(__file__))
NAV_DIR = os.path.join(HERE, "data")
HOLDINGS = os.path.join(HERE, "data", "holdings.json")


def load(code):
    path = os.path.join(NAV_DIR, f"{code.upper()}.csv")
    rows = list(csv.DictReader(open(path)))
    return [(datetime.date.fromisoformat(r["date"]), float(r["nav"])) for r in rows]


def trailing(pts, months):
    end = pts[-1][0]
    start = end - datetime.timedelta(days=30 * months)
    prior = [x for x in pts if x[0] <= start]
    if len(prior) < 2:
        return None
    span = (end - prior[-1][0]).days
    return (pts[-1][1] / prior[-1][1]) ** (365 / span) - 1 if span > 0 else None


def ann_return(pts):
    v0, v1 = pts[0][1], pts[-1][1]
    span = (pts[-1][0] - pts[0][0]).days
    return (v1 / v0) ** (365 / span) - 1 if span > 0 else None


def stats(pts):
    """-> (成立年化, sharpe, 最大回撤)"""
    v = np.array([x[1] for x in pts])
    ann = ann_return(pts)
    ret = v[1:] / v[:-1] - 1
    step = np.median([(b[0] - a[0]).days for a, b in zip(pts, pts[1:])])
    vol = ret.std(ddof=1) * math.sqrt(365 / step)
    sharpe = (ann - RF) / vol if vol > 0 else None
    mdd = ((v / np.maximum.accumulate(v)) - 1).min()
    return ann, sharpe, mdd


def since(pts, days, min_points=50):
    sub = [x for x in pts if x[0] >= pts[-1][0] - datetime.timedelta(days=days)]
    return sub if len(sub) >= min_points else None


def pct(x):
    return f"{x:+.2%}" if x is not None else "--"


_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9}


def _cn2int(s):
    """中文/阿拉伯数字 → int（支持 三百七十/三十/六/370）。"""
    if s.isdigit():
        return int(s)
    total, section = 0, 0
    for ch in s:
        if ch in _CN_NUM:
            section += _CN_NUM[ch]
        elif ch == "十":
            section = (section or 1) * 10
        elif ch == "百":
            section = (section or 1) * 100
        elif ch == "千":
            section = (section or 1) * 1000
        total += section if ch in "千百十" else 0
        if ch in "千百十":
            section = 0
    return total + section


_UNIT_DAYS = {"天": 1, "月": 30, "年": 365}


def open_rule(name, info):
    """-> (规则文案, 最低持有天数|None)：接口 open_rule 优先，产品名兜底。"""
    rule = info.extra.get("open_rule") if info else ""
    m_days = None
    if rule:
        m = re.search(r"([0-9一二三四五六七八九十百千]+)(天|个月|月|年)", rule)
        if m:
            m_days = _cn2int(m.group(1)) * _UNIT_DAYS[m.group(2)[-1]]
            return rule, m_days
        return rule, None  # 如「每季开放」，无固定持有天数
    name = name or ""
    if "日开" in name:
        rule = "每日开放"
        m = re.search(r"([0-9一二三四五六七八九十百千]+)(年|个?月|天)(?:最短|最低)?持有", name)
        if m:
            m_days = _cn2int(m.group(1)) * _UNIT_DAYS[m.group(2)[-1]]
            rule = f"最低持有{m.group(1)}{m.group(2)}后每日开放"
        return rule, m_days
    m = re.search(r"([0-9一二三四五六七八九十百千]+)(天|个?月|年)(?:最短|最低)?持有期", name)
    if m:
        m_days = _cn2int(m.group(1)) * _UNIT_DAYS[m.group(2)[-1]]
        return f"最低持有{m.group(1)}{m.group(2)}", m_days
    return "", None


def build_report(no_refresh=False):
    """-> 完整速览 markdown 文本（要点按近3月年化降序，末尾合计）。"""
    holdings = json.load(open(HOLDINGS, encoding="utf-8"))
    if not no_refresh:
        subprocess.run([sys.executable, os.path.join(HERE, "fetch_nav_history.py"),
                        "--out", NAV_DIR, *holdings.keys()], check=False)
    rows = []
    for code, h in holdings.items():
        code = code.upper()
        try:
            pts = load(code)
        except FileNotFoundError:
            rows.append({"sort": -9e9, "code": code, "err": "无净值数据"})
            continue
        try:
            info = None
            for _ in range(2):  # 接口偶发抖动，重试一次
                try:
                    info = convert(code)
                    break
                except Exception:
                    pass
            name = info.name or code if info else code
            risk = (info.extra.get("risk") or "") if info else ""
            m = re.search(r"(PR?\d)", risk)
            risk = m.group(1) if m else risk[:6]
        except Exception:
            name, risk = code, ""
        name = name if len(name) <= 24 else name[:23] + "…"
        date, nav = pts[-1]
        mv = nav * h["shares"]
        pnl = mv - h["principal"]
        days = (date - datetime.date.fromisoformat(h["buy_date"])).days
        ann_h = (mv / h["principal"]) ** (365 / days) - 1 if days > 0 else None
        span = (pts[-1][0] - pts[0][0]).days
        dur = f"{span//365}年{span%365}天" if span >= 365 else f"{span}天"
        p_ann, p_sp, mdd = stats(pts)
        t6 = trailing(pts, 6)
        y = since(pts, 365)
        sp1y = stats(y)[1] if y else None
        m3 = trailing(pts, 3)
        rule, rule_days = open_rule((info.name if info else None) or name, info)
        if rule_days is not None:
            redeem_date = datetime.date.fromisoformat(h["buy_date"]) + \
                datetime.timedelta(days=rule_days)
            left = (redeem_date - date).days
            rule += (f"（{redeem_date.isoformat()}起可赎）" if left <= 0
                     else f"（{redeem_date.isoformat()}可赎，还差{left}天）")
        elif rule.startswith("每"):
            # 周期开放型：按净值发布节奏外推下次开放日（净值仅在开放日更新）
            gaps = [(b[0] - a[0]).days for a, b in zip(pts[-9:], pts[-8:])]
            if gaps:
                cadence = int(np.median(gaps))
                nxt = pts[-1][0]
                today = datetime.date.today()
                while nxt <= today:
                    nxt += datetime.timedelta(days=cadence)
                rule += f"（下次开放约{nxt.isoformat()}，约{cadence}天一次）"
        m = re.search(r"(PR?\d)", risk)
        risk = m.group(1) if m else risk[:6]
        # 短名：去掉「理财/计划/持有期/固定收益类」等套话
        short = re.sub(r"(理财|计划|持有期|固定收益类|增强型|混合类)", "", name)
        short = re.sub(r"[0-9]+号", "", short)
        short = short[:14]
        # 开放状态行：⏳/✅ 前缀 + 日期
        if "还差" in rule:
            mm = re.search(r"（(.+?)可赎，还差(\d+)天）", rule)
            base = re.search(r"^[^（]+", rule).group(0).rstrip("（")
            open_line = f"⏳ {mm.group(1)} 可赎（还差{mm.group(2)}天）｜{base}"
        elif "起可赎" in rule:
            mm = re.search(r"（(.+?)起可赎）", rule)
            base = rule.split("（")[0]
            open_line = f"✅ 已可赎（{mm.group(1)}起）｜{base}"
        elif rule.startswith("每日开放"):
            open_line = "✅ 每日开放"
        else:
            open_line = f"✅ {rule}"  # 每季开放等周期型
        rows.append({
            "sort": m3 if m3 is not None else -9e9,
            "code": code,
            "err": None,
            "name": name,
            "risk": risk or "风险?",
            "days": days,
            "open_line": open_line,
            "short": short,
            "total": pct(pnl / h["principal"]),
            "ann_h": pct(ann_h),
            "m1": pct(trailing(pts, 1)),
            "m3": pct(m3),
            "t6": pct(t6),
            "p_ann": pct(p_ann),
            "mdd": pct(mdd),
            "p_sp": f"{p_sp:.2f}" if p_sp is not None else "--",
            "sp1y": f"{sp1y:.2f}" if sp1y is not None else "--",
            "dur": dur,
        })
    rows.sort(key=lambda r: r["sort"], reverse=True)
    tot_p = sum(h["principal"] for h in holdings.values())
    tot_v = 0.0
    for r in rows:
        try:
            pts = load(r["code"])
            tot_v += pts[-1][1] * holdings[r["code"]]["shares"]
        except (FileNotFoundError, KeyError):
            pass
    lines = []
    upcoming = sorted((r for r in rows if r.get("open_line", "").startswith("⏳")),
                      key=lambda r: int(re.search(r"还差(\d+)天", r["open_line"]).group(1)))
    if upcoming:
        lines.append("## ⏰ 赎回提醒\n")
        for r in upcoming[:3]:
            mm = re.search(r"⏳ (.+?) 可赎（还差(\d+)天）", r["open_line"])
            lines.append(f"> - **{r['short']}**　{mm.group(1)} 可赎，还差 {mm.group(2)} 天")
        lines.append("\n---\n")
    for r in rows:
        if r.get("err"):
            lines.append(f"**{r['code']}**：{r['err']}\n")
            continue
        lines.append(f"**{r['short']}**（{r['code']} · {r['risk']} · 持有{r['days']}天）\n"
                     f"- {r['open_line']}\n"
                     f"- 收益 {r['total']}｜年化 {r['ann_h']}｜近1月 {r['m1']}｜近3月 {r['m3']}\n"
                     f"- 成立年化 {r['p_ann']}｜最大回撤 {r['mdd']}"
                     f"｜Sharpe(成立/近1年) {r['p_sp']}/{r['sp1y']}\n")
    lines.append("---\n"
                 "*注：Sharpe =（年化收益−1.5%无风险）÷年化波动，越高越好；"
                 "年化含持有年化/近6月/成立口径；回撤为历史最大跌幅。*\n")
    return "\n".join(lines)


def load_holdings():
    return json.load(open(HOLDINGS, encoding="utf8"))

def save_holdings(h):
    json.dump(h, open(HOLDINGS, "w", encoding="utf8"), ensure_ascii=False, indent=2)

def cmd_buy(code, shares, principal, buy_date):
    h = load_holdings()
    h[code] = {"shares": shares, "principal": principal, "buy_date": buy_date}
    save_holdings(h)
    print(f"买入: {code} 份额={shares} 本金={principal} 日期={buy_date}")
    print(f"当前持仓 {len(h)} 只")

def cmd_redeem(code, date):
    h = load_holdings()
    if code not in h:
        print(f"持仓中无 {code}")
        return
    rec = h.pop(code)
    rec["redeem_date"] = date
    red_path = os.path.join(HERE, "data", "redeemed.json")
    redeemed = json.load(open(red_path, encoding="utf8")) if os.path.exists(red_path) else {}
    redeemed[code] = rec
    json.dump(redeemed, open(red_path, "w", encoding="utf8"), ensure_ascii=False, indent=2)
    save_holdings(h)
    print(f"赎回: {code}（{rec.get('principal','')}元, 买入{rec.get('buy_date','')}）")
    print(f"当前持仓 {len(h)} 只")

def cmd_expiring(days):
    h = load_holdings()
    today = datetime.date.today()
    # 杭银自营的 endDate 在 on_sale.py 数据里，其他管理人查各自接口
    # 简化：从 bank-wealth-screening 的 on_sale.py/on_sale_hzbank.py 数据源查
    # 这里先用 holdings 里手动标记的到期日
    print(f"检查未来 {days} 天内到期的持仓（{today} + {days}d）...")
    print()
    for code, info in sorted(h.items()):
        print(f"  {code} 买入{info.get('buy_date','')}")
    print(f"\n提示: 到期日需从各管理人官网/银行App查询，本工具暂不支持自动检测。")
    print(f"建议定期在银行App查看产品到期日期。")

def main():
    ap = argparse.ArgumentParser(description="个人理财产品持仓管理")
    ap.add_argument("--no-refresh", action="store_true",
                    help="跳过拉取，直接用本地缓存的历史净值")
    ap.add_argument("--buy", metavar="CODE", help="买入记账：产品代码")
    ap.add_argument("--shares", type=float, help="买入份额")
    ap.add_argument("--principal", type=float, help="买入本金")
    ap.add_argument("--date", help="买入/赎回日期 (YYYY-MM-DD)")
    ap.add_argument("--redeem", metavar="CODE", help="赎回销账：产品代码")
    ap.add_argument("--expiring", type=int, metavar="N", help="检查未来N天内到期的持仓")
    args = ap.parse_args()

    if args.buy:
        if not args.shares or not args.principal:
            ap.error("--buy 需要 --shares 和 --principal")
        cmd_buy(args.buy, args.shares, args.principal, args.date or datetime.date.today().isoformat())
    elif args.redeem:
        cmd_redeem(args.redeem, args.date or datetime.date.today().isoformat())
    elif args.expiring:
        cmd_expiring(args.expiring)
    else:
        print(build_report(no_refresh=args.no_refresh))


if __name__ == "__main__":
    main()
