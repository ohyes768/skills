"""
TradeSmart 数据源适配器

获取 lowrisktradesmart.org 的港股新股中签金额数据。
提供每只新股不同申购股数对应的资金需求。

数据来源: https://lowrisktradesmart.org/api/ipos
"""

import re
from typing import Optional

import httpx


# 常量
TRADESMART_API_URL = "https://lowrisktradesmart.org/api/ipos"
TRADESMART_TRACKER_URL = "https://www.lowrisktradesmart.org/zh/tools/ipo-tracker"
REQUEST_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _normalize_ipo(raw: dict) -> dict:
    """将原始 API 数据标准化为 snake_case 字典
    
    Args:
        raw: API 返回的原始 IPO 数据
        
    Returns:
        标准化后的字典
    """
    # flatPairs: [{"shares": 100, "amount": 2915.1}, ...]
    flat_pairs = raw.get("flatPairs") or []
    
    return {
        "id": raw.get("id"),
        "company_name": raw.get("companyName"),
        "public_offer_shares": _safe_int(raw.get("publicOfferShares")),
        "group_b_ratio": raw.get("groupBRatio"),
        "sort_order": raw.get("sortOrder"),
        "flat_pairs": [
            {"shares": p.get("shares"), "amount": p.get("amount")}
            for p in flat_pairs
        ],
    }


def _safe_int(val) -> Optional[int]:
    """安全转换为整数"""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def fetch_tradesmart_ipos() -> list[dict]:
    """获取 TradeSmart 当前 IPO 列表
    
    从 lowrisktradesmart.org API 获取所有在列 IPO 的中签金额数据。
    每只 IPO 包含不同申购股数对应的入场金额（含手续费）。
    
    Returns:
        标准化后的 IPO 字典列表，按 sort_order 排序
        
    Raises:
        requests.RequestException: 网络请求失败
        ValueError: API 返回数据格式异常
        
    Example:
        >>> ipos = fetch_tradesmart_ipos()
        >>> for ipo in ipos[:3]:
        ...     print(f"{ipo['company_name']}: {len(ipo['flat_pairs'])} 档位")
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    
    response = httpx.get(
        TRADESMART_API_URL, 
        headers=headers, 
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    
    data = response.json()
    
    if not isinstance(data, dict) or "items" not in data:
        raise ValueError(f"API 返回格式异常: 缺少 'items' 字段")
    
    items = data["items"]
    if not isinstance(items, list):
        raise ValueError(f"API 返回格式异常: 'items' 不是列表")
    
    return [_normalize_ipo(item) for item in items]


def fetch_tracker_margin_records() -> list[dict]:
    """解析 IPO Tracker 页面嵌入的实时孖展记录。"""
    response = httpx.get(
        TRADESMART_TRACKER_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    pattern = re.compile(
        r'\\"symbol\\":\\"(?P<symbol>\d{5})\\"'
        r'.{0,400}?\\"name\\":\\"(?P<name>[^"\\]+)\\"'
        r'.{0,500}?\\"margin_total_hkd_yi\\":(?P<margin>[0-9.]+)'
        r'.{0,160}?\\"oversubscription_ratio\\":(?P<oversub>[0-9.]+)'
        r'.{0,300}?\\"broker_top_text\\":(?P<broker>null|\\"[^"\\]*\\")'
        r'.{0,200}?\\"observed_at\\":\\"(?P<observed>[^"\\]+)\\"',
        re.DOTALL,
    )
    records = []
    for match in pattern.finditer(response.text):
        broker_raw = match.group("broker")
        records.append({
            "symbol": match.group("symbol"),
            "symbol_hk": f"{match.group('symbol')}.HK",
            "name": match.group("name"),
            "margin_total_hkd_yi": float(match.group("margin")),
            "oversubscription_ratio": float(match.group("oversub")),
            "broker_top_text": None if broker_raw == "null" else broker_raw[2:-2],
            "observed_at": match.group("observed"),
            "tracker_url": TRADESMART_TRACKER_URL,
        })
    if not records:
        raise ValueError("IPO Tracker 页面未找到孖展嵌入数据")
    return records


def get_tracker_margin(code: str) -> Optional[dict]:
    """按五位股票代码获取 Tracker 孖展记录。"""
    normalized = re.sub(r"\D", "", code).zfill(5)
    return next((item for item in fetch_tracker_margin_records() if item["symbol"] == normalized), None)


def _parse_json_scalar(raw: str, kind: str):
    """把 TradeSmart 嵌入 JSON 中捕获的 raw 值转成 None/int/float/str。

    招股结束后 TradeSmart 会把 offer_price_range / lot_size / entry_fee_hkd /
    hk_offer_shares 置为 null；招股期内则为转义字符串或数字。
    """
    if raw is None:
        return None
    s = raw.strip()
    if s == "null":
        return None
    # 去掉转义的双引号：\\"123\\" → 123
    if s.startswith('\\"') and s.endswith('\\"'):
        s = s[2:-2]
    if kind == "int":
        try:
            return int(s)
        except ValueError:
            return None
    if kind == "float":
        try:
            return float(s)
        except ValueError:
            return None
    return s or None


def get_tracker_ipo(code: str) -> Optional[dict]:
    """从 Tracker 页面读取单只 IPO 的招股条款。

    注意：TradeSmart 在招股截止后会把价格/股数类字段（offer_price_range /
    lot_size / entry_fee_hkd / hk_offer_shares）置为 null。日期类字段
    （subscription_open / subscription_close / listing_date）则长期保留。
    本函数因此对价格/股数字段允许 null，仅日期字段缺失时才返回 None。
    """
    normalized = re.sub(r"\D", "", code).zfill(5)
    response = httpx.get(
        TRADESMART_TRACKER_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    escaped = re.escape(normalized)
    pattern = re.compile(
        rf'\\"symbol\\":\\"{escaped}\\"'
        r'.{0,200}?\\"name\\":\\"(?P<name>[^"\\]+)\\"'
        r'.{0,200}?\\"subscription_open\\":\\"(?P<open>[^"\\]+)\\"'
        r'.{0,200}?\\"subscription_close\\":\\"(?P<close>[^"\\]+)\\"'
        r'.{0,500}?\\"listing_date\\":\\"(?P<listing>[^"\\]+)\\"'
        r'.{0,2500}?\\"offer_price_range\\":(?P<price>[^,}]+)'
        r'.{0,200}?\\"lot_size\\":(?P<lot>[^,}]+)'
        r'.{0,200}?\\"entry_fee_hkd\\":(?P<fee>[^,}]+)'
        r'.{0,200}?\\"hk_offer_shares\\":(?P<shares>[^,}]+)',
        re.DOTALL,
    )
    match = pattern.search(response.text)
    if not match:
        return None
    return {
        "symbol": normalized,
        "name": match.group("name"),
        "subscription_open": match.group("open"),
        "subscription_close": match.group("close"),
        "listing_date": match.group("listing"),
        "offer_price_range": _parse_json_scalar(match.group("price"), "str"),
        "lot_size": _parse_json_scalar(match.group("lot"), "int"),
        "entry_fee_hkd": _parse_json_scalar(match.group("fee"), "float"),
        "hk_offer_shares": _parse_json_scalar(match.group("shares"), "int"),
        "tracker_url": TRADESMART_TRACKER_URL,
    }


def get_tradesmart_ipo(company_name: str) -> Optional[dict]:
    """按公司名查找单只 IPO 数据
    
    支持模糊匹配（包含关系），大小写不敏感。
    
    Args:
        company_name: 公司名称（支持部分匹配）
        
    Returns:
        找到返回标准化的 IPO 字典，未找到返回 None
        
    Raises:
        requests.RequestException: 网络请求失败
        
    Example:
        >>> ipo = get_tradesmart_ipo("美格")
        >>> if ipo:
        ...     print(f"公发股数: {ipo['public_offer_shares']:,}")
        ...     for tier in ipo['flat_pairs'][:3]:
        ...         print(f"  {tier['shares']:,} 股 → {tier['amount']:,.2f} HKD")
    """
    ipos = fetch_tradesmart_ipos()
    
    search_lower = company_name.lower()
    
    for ipo in ipos:
        name = ipo.get("company_name") or ""
        if search_lower in name.lower():
            return ipo
    
    return None


def get_entry_amount(ipo: dict, shares: int) -> Optional[float]:
    """查询指定股数的入场金额
    
    Args:
        ipo: IPO 数据字典（来自 fetch_tradesmart_ipos 或 get_tradesmart_ipo）
        shares: 申购股数
        
    Returns:
        对应的入场金额（含手续费），未找到对应档位返回 None
        
    Example:
        >>> ipo = get_tradesmart_ipo("美格智能")
        >>> amount = get_entry_amount(ipo, 100)
        >>> print(f"入场金额: {amount:,.2f} HKD")
    """
    flat_pairs = ipo.get("flat_pairs") or []
    
    for tier in flat_pairs:
        if tier.get("shares") == shares:
            return tier.get("amount")
    
    return None


def main(argv=None):
    """CLI 入口"""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="TradeSmart 港股新股入场费数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tradesmart.py list                     # 当前 IPO 列表
  python tradesmart.py detail 美格              # 按名称查找
  python tradesmart.py detail 美格 --shares 100 # 查询入场金额
  python tradesmart.py list --json              # JSON 输出
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # list 命令
    list_parser = subparsers.add_parser("list", help="当前 IPO 列表")
    list_parser.add_argument("--limit", type=int, default=10, help="返回数量 (默认 10)")
    list_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    # detail 命令
    detail_parser = subparsers.add_parser("detail", help="按名称查找 IPO")
    detail_parser.add_argument("name", help="公司名称（支持模糊匹配）")
    detail_parser.add_argument("--shares", type=int, help="查询指定股数的入场金额")
    detail_parser.add_argument("--json", action="store_true", help="JSON 格式输出")

    tracker_parser = subparsers.add_parser("tracker", help="IPO Tracker 实时孖展数据")
    tracker_parser.add_argument("code", nargs="?", help="五位股票代码；省略则返回全部")

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            ipos = fetch_tradesmart_ipos()
            if args.json:
                print(json.dumps(ipos[:args.limit], ensure_ascii=False, indent=2))
            else:
                for ipo in ipos[:args.limit]:
                    name = ipo["company_name"]
                    public_shares = ipo["public_offer_shares"]
                    tiers = ipo["flat_pairs"]
                    shares_str = f"{public_shares:,}" if public_shares else "--"
                    first_tier = f"{tiers[0]['shares']:,}股→{tiers[0]['amount']:,.0f}HKD" if tiers else "--"
                    print(f"{name:<20} 公发: {shares_str:>15} 最低档: {first_tier}")

        elif args.command == "detail":
            ipo = get_tradesmart_ipo(args.name)
            if not ipo:
                print(f"未找到: {args.name}", file=sys.stderr)
                sys.exit(1)

            if args.json:
                print(json.dumps(ipo, ensure_ascii=False, indent=2))
            else:
                print(f"公司: {ipo['company_name']}")
                public = ipo['public_offer_shares']
                print(f"公发股数: {public:,}" if public else "公发股数: --")
                print(f"\n{'股数':>10} {'入场金额':>15}")
                print("-" * 28)
                for tier in ipo["flat_pairs"]:
                    print(f"{tier['shares']:>10,} {tier['amount']:>15,.2f}")

            if args.shares:
                amount = get_entry_amount(ipo, args.shares)
                if amount:
                    print(f"\n{args.shares:,} 股入场金额: {amount:,.2f} HKD")
                else:
                    print(f"\n未找到 {args.shares:,} 股对应档位")

        elif args.command == "tracker":
            result = get_tracker_margin(args.code) if args.code else fetch_tracker_margin_records()
            print(json.dumps(result, ensure_ascii=False, indent=2))

    except httpx.HTTPError as e:
        print(f"网络错误: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"数据错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
