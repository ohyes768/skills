#!/usr/bin/env python3
"""港股打新研究助手 CLI（TradeSmart 主数据源）。"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


HELP = """
港股打新研究助手 CLI

主要命令:
  overview                              当前实时孖展概览
  analyze <代码>                        TradeSmart 单股聚合分析
  margin [代码]                         实时孖展；等同 tradesmart tracker
  tradesmart tracker [代码]             孖展总额、预计超购、观测时间
  tradesmart list|detail                 申购金额档位
  jisilu list|detail                     历史 IPO
  odds --oversub <倍数> --price <价格>   中签率预测
  hkex active                            港交所活跃申请
  sentiment ...                          市场情绪及保荐人
  etnet list|search                      经济通保荐人统计
  futu ...                               富途历史数据
  ah compare ...                         A+H 折价

实时数据默认来自 TradeSmart；官方条款使用港交所文件复核。
"""


def show_overview() -> None:
    from tradesmart import fetch_tracker_margin_records

    records = fetch_tracker_margin_records()
    print("当前招股 IPO 孖展一览（TradeSmart）")
    print("=" * 68)
    for item in records:
        print(f"\n{item['name']} ({item['symbol_hk']})")
        print(f"  孖展总额: {item['margin_total_hkd_yi']:.2f} 亿港元")
        print(f"  预计超购: {item['oversubscription_ratio']:.2f} 倍")
        print(f"  数据时点: {item['observed_at']}")


def analyze(code: str) -> None:
    from tradesmart import get_tracker_ipo, get_tracker_margin

    tracker = get_tracker_margin(code)
    if not tracker:
        print(json.dumps({"code": code, "status": "not_found", "source": "TradeSmart"}, ensure_ascii=False, indent=2))
        return
    terms = get_tracker_ipo(code)
    result = {
        "code": tracker["symbol"],
        "name": tracker["name"],
        "margin": {
            "total_billion": round(tracker["margin_total_hkd_yi"], 2),
            "oversubscription_forecast": round(tracker["oversubscription_ratio"], 2),
            "observed_at": tracker["observed_at"],
            "broker_summary": tracker.get("broker_top_text"),
        },
        "subscription": {
            "offer_price_range": terms.get("offer_price_range") if terms else None,
            "subscription_open": terms.get("subscription_open") if terms else None,
            "subscription_close": terms.get("subscription_close") if terms else None,
            "listing_date": terms.get("listing_date") if terms else None,
            "public_offer_shares": terms.get("hk_offer_shares") if terms else None,
            "minimum_shares": terms.get("lot_size") if terms else None,
            "minimum_amount_hkd": terms.get("entry_fee_hkd") if terms else None,
        },
        "sources": [tracker["tracker_url"]],
        "missing": ["broker_breakdown", "cornerstone", "agency_rating", "sponsor"],
        "note": "缺失字段应从港交所招股章程及其他公开来源交叉补充。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def odds(args: list[str]) -> None:
    from allotment import IPOData, predict_allotment_table

    oversub, price, lot_size, mechanism = 100.0, 10.0, 500, "A"
    output_json = "--json" in args
    for i, arg in enumerate(args):
        if arg == "--oversub" and i + 1 < len(args): oversub = float(args[i + 1])
        elif arg == "--price" and i + 1 < len(args): price = float(args[i + 1])
        elif arg == "--lot-size" and i + 1 < len(args): lot_size = int(args[i + 1])
        elif arg == "--mechanism" and i + 1 < len(args): mechanism = args[i + 1].upper()
    entry_fee = lot_size * price * 1.01
    data: IPOData = {"offer_price": price, "lot_size": lot_size, "entry_fee": entry_fee, "mechanism": mechanism}
    results = predict_allotment_table(data, oversub)
    if output_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print(f"中签率表格（超购 {oversub}x，机制{mechanism}）\n")
    print(f"{'手数':>6} │ {'金额':>12} │ {'中签率':>8} │ 分组")
    for row in results:
        print(f"{row['lots']:>6} │ {int(entry_fee * row['lots']):>12,} │ {row['probability_pct']:>8} │ {row['group']}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help", "help"}:
        print(HELP)
        return
    module, rest = args[0], args[1:]
    if module == "overview":
        show_overview()
    elif module == "analyze":
        if not rest: raise SystemExit("用法: hkipo analyze <代码>")
        analyze(rest[0])
    elif module == "margin":
        from tradesmart import main as tradesmart_main
        tradesmart_main(["tracker", *rest])
    elif module == "tradesmart":
        from tradesmart import main as tradesmart_main
        tradesmart_main(rest)
    elif module == "jisilu":
        from jisilu import main as handler
        handler(rest)
    elif module == "futu":
        from futu import main as handler
        handler(rest)
    elif module == "allotment":
        from allotment import main as handler
        handler(rest)
    elif module == "odds":
        odds(rest)
    elif module == "sentiment":
        from sentiment import main as handler
        handler(rest)
    elif module == "hkex":
        from hkex import fetch_hkex_active_ipos_sync, get_prospectus_url
        if not rest or rest[0] != "active": raise SystemExit("用法: hkipo hkex active")
        for ipo in fetch_hkex_active_ipos_sync()[:10]:
            print(json.dumps({"name": ipo.name, "code": ipo.stock_code, "status": ipo.status_cn, "prospectus": get_prospectus_url(ipo)}, ensure_ascii=False))
    elif module == "etnet":
        from etnet import main as handler
        handler(rest)
    elif module == "ah":
        from ah import fetch_ah_comparison
        if not rest or rest[0] != "compare": raise SystemExit("用法: hkipo ah compare <代码> --price <价格> --name <名称>")
        code, price, name = rest[1], float(rest[rest.index("--price") + 1]), rest[rest.index("--name") + 1]
        print(json.dumps(fetch_ah_comparison(code, price, name), ensure_ascii=False, indent=2))
    else:
        raise SystemExit(f"未知命令: {module}\n{HELP}")


if __name__ == "__main__":
    main()
