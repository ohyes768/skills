"""黄金推送的固定事实栏目；预览和发送使用同一消息。"""
from math import isfinite


def _time(value):
    return value.replace("T", " ").replace("+08:00", "") if value else "未知"


def format_fed_expectations(report):
    report = report or {}
    status = report.get("status", "unavailable")
    lines = ["### 美联储利率预期"]
    if status == "unavailable":
        return "\n".join(lines + ["金十数据暂缺，本次不判断利率预期方向。"])
    lines.append(f"来源：金十数据｜发布：{_time(report.get('published_at'))}（北京时间）")
    if status == "awaiting_update":
        return "\n".join(lines + ["已到快照中的议息日，等待会后新快照；暂不沿用旧概率。"])
    notes = {"cached": "快照未更新（使用一小时内已获取的数据）。",
             "fallback": "本次获取失败或回退，沿用缓存；暂不判断当前方向。",
             "stale": "快照已过期（超过96小时），仅作历史参考，不判断当前方向。"}
    if status in notes:
        lines.append(notes[status])
    elif not report.get("is_new_snapshot"):
        lines.append("快照未更新，以下仍为同一组日快照比较。")
    meetings = report.get("meetings", [])
    if not meetings:
        return "\n".join(lines + ["未来会议数据暂缺。"])
    first = meetings[0]
    lines.append(f"\n下次会议：{first['meeting_date']}（美国日期）")
    lines.append(f"- 降息 {first['cut_pct']:.1f}%｜维持 {first['hold_pct']:.1f}%｜加息 {first['hike_pct']:.1f}%")
    change = first.get("change")
    if change:
        lines.append(f"- 较上一发布日期快照（{_time(change['baseline_published_at'])} 北京时间）："
                     f"降息 {change['cut_pp']:+.1f}、维持 {change['hold_pp']:+.1f}、加息 {change['hike_pp']:+.1f} 个百分点。")
        lines.append(f"- 概率加权预期利率变化：{change['expected_rate_bps']:+.2f} 个基点。")
    else:
        lines.append("- 缺少同一会议、相同当前利率的前一发布日期快照，暂不比较变化。")
    interpretation = {"hawkish": "预期偏鹰，可能增加黄金压力；需结合价格表现确认。",
                      "dovish": "预期偏鸽，可能支持黄金；需结合价格表现确认。",
                      "unchanged": "预期利率基本未变，新增方向信息有限。"}
    if status in ("fresh", "cached") and first.get("direction") in interpretation:
        lines.append(interpretation[first["direction"]])
    lines.append("\n未来会议预期利率（概率加权中点，反映累计路径，不代表该次会议单独加减息）：")
    for meeting in meetings:
        delta = meeting.get("change")
        comparison = f"，较前一发布日期 {delta['expected_rate_bps']:+.2f} 基点" if delta else "，比较基准暂缺"
        lines.append(f"- {meeting['meeting_date']}：{meeting['expected_rate_pct']:.4f}%{comparison}")
    if report.get("warnings"):
        lines.append("数据提示：" + "；".join(report["warnings"]))
    return "\n".join(lines)


def _number(value, *, signed=False):
    try:
        value = float(value)
        if not isfinite(value):
            return "暂缺"
        return f"{value:+.2f}" if signed else f"{value:.2f}"
    except (TypeError, ValueError, OverflowError):
        return "暂缺"


def _change(value):
    text = _number(value, signed=True)
    return text + "%" if text != "暂缺" else text


def format_fed_summary(report):
    """复用同一快照可靠性规则，仅保留下次会议与关键比较。"""
    full = format_fed_expectations(report)
    compact = full.split("\n未来会议预期利率", 1)[0].strip()
    # 概率加权变化携带精确基准，避免逐项概率变化占用黄金主体篇幅。
    lines = [line for line in compact.splitlines()
             if not line.startswith("- 较上一发布日期快照")]
    meetings = (report or {}).get("meetings", [])
    if meetings and meetings[0].get("change"):
        change = meetings[0]["change"]
        lines = [line.replace("个基点。", f"个基点（较{_time(change['baseline_published_at'])}北京时间）。")
                 if line.startswith("- 概率加权") else line for line in lines]
    warnings = (report or {}).get("warnings")
    if warnings and "数据提示：" not in compact:
        lines.append("数据提示：" + "；".join(warnings))
    return "\n".join(lines).replace("### 美联储利率预期", "### 附录：美联储利率预期", 1)


def format_price_summary(summary):
    summary = summary or {}
    if summary.get("status", "unavailable") == "unavailable":
        return "国内历史日线暂缺，涨跌幅、均线与区间暂不判断。"
    end = summary["last_close_date"]
    lines = []
    if summary.get("status") == "stale":
        lines.append("**日线已陈旧，以下仅供历史参考，不判断当前技术趋势。**")
    lines.append(f"较最近收盘（{end}）：{_change(summary.get('quote_change_pct'))}")
    day_baseline = summary.get("previous_close_date")
    if day_baseline:
        lines.append(f"收盘日涨跌：{_change(summary.get('day_change_pct'))}（{day_baseline} → {end}）")
    else:
        lines.append("收盘日涨跌：暂缺前一交易日")
    five_baseline = summary.get("five_day_start_date")
    if five_baseline:
        lines.append(f"5交易日涨跌：{_change(summary.get('five_day_change_pct'))}（{five_baseline} → {end}）")
    else:
        lines.append("5交易日涨跌：样本不足6个收盘")
    return "\n\n".join(lines)


def format_technical_reference(gold_data):
    summary = gold_data.get("price_summary") or {}
    end = summary.get("last_close_date") or "日期暂缺"
    suffix = "；仅供历史参考" if summary.get("status") == "stale" else ""
    lines = [f"### 技术参考（日线截至{end}{suffix}）", f"**Wilder RSI(14)：{_number(gold_data.get('gold_rsi_14'))}**"]
    for key, label in [("ma5", "MA5"), ("ma20", "MA20")]:
        value = summary.get(key)
        text = f"{label}：{_number(value)}"
        if value is not None and summary.get("last_close") is not None:
            close = summary["last_close"]
            position = "上方" if close > value else "下方" if close < value else "附近"
            text += f"元/克，最近收盘位于{position}"
        else:
            text += "（样本不足或日线暂缺）"
        lines.append(text)
    if summary.get("range_count"):
        lines.append(f"近期{summary['range_count']}交易日{summary['range_kind']}："
                     f"{_number(summary['range_low'])}—{_number(summary['range_high'])}元/克"
                     f"（{summary['range_start_date']} → {summary['range_end_date']}）；仅作历史区域参考。")
    else:
        lines.append("近期区间：暂缺")
    lines.append(f"口径对照：Simple RSI(14) {_number(gold_data.get('simple_rsi_14'))}｜"
                 f"第三方RSI(14) {_number(gold_data.get('ali_rsi_14'))}（来源/计算口径可能不同）")
    if summary.get("warnings"):
        lines.append("数据提示：" + "；".join(summary["warnings"]))
    return "\n\n".join(lines)


def build_gold_markdown(gold_data, analysis):
    return (f"## 黄金走势研判\n\n"
            f"**国内Au9999：{_number(gold_data.get('gold_price'))} 元/克**｜"
            f"**国际现货：{_number(gold_data.get('xau_usd'))} 美元/盎司**\n\n"
            f"采集：{gold_data.get('time', '时间暂缺')}（北京时间）\n\n"
            f"{format_price_summary(gold_data.get('price_summary'))}\n\n"
            f"### 黄金分析\n\n{analysis}\n\n"
            f"{format_technical_reference(gold_data)}\n\n"
            f"{format_fed_summary(gold_data.get('fed_expectations'))}\n")
