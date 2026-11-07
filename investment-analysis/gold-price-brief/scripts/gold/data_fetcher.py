"""
数据获取模块 - 从各数据源获取黄金相关数据
"""

import os
import json
import urllib.parse
import requests
import pandas as pd
from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional

from .fed_cache import get_fed_expectations
from .fed_expectations import china_now
from .holdings import get_gld_holdings_history
from .technicals import build_price_summary, normalize_candles, build_holdings_summary, positive_number


# 阿里云 API 配置
ALI_API_HOST = "alirmcom2.market.alicloudapi.com"


def _get_ali_headers() -> dict:
    """获取阿里云 API 请求头"""
    api_code = os.environ.get("ALI_API_CODE")
    if not api_code:
        raise ValueError("阿里云 API Code 未设置，请设置 ALI_API_CODE 环境变量")
    return {"Authorization": f"APPCODE {api_code}"}


def get_gold_price_now() -> float:
    """
    获取当前黄金价格（上海Au9999）

    Returns:
        黄金价格（元/克）
    """
    url = f"https://{ALI_API_HOST}/query/com?symbol=SGEAU9999"
    response = requests.get(url, headers=_get_ali_headers(), timeout=10)
    gold_data = response.json()["Obj"]["P"]
    return float(gold_data)


def get_xau_usd_price() -> float:
    """
    获取国际黄金现货价格（XAUUSD）

    Returns:
        黄金价格（美元/盎司）
    """
    url = f"https://{ALI_API_HOST}/query/com?symbol=XAUUSD"
    response = requests.get(url, headers=_get_ali_headers(), timeout=10)
    gold_data = response.json()["Obj"]["P"]
    return float(gold_data)


def get_gold_kline_data() -> list:
    """
    获取黄金K线数据（阿里云 D 周期接口固定返回 ~3 个月窗口，约 53 个交易日）

    Returns:
        K线数据列表，每项包含 D(日期)、C(收盘价)、H(最高价) 等
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://{ALI_API_HOST}/query/comkm4?symbol=SGEAU9999&period=D&date={yesterday}"
    response = requests.get(url, headers=_get_ali_headers(), timeout=10)
    kline_data = response.json().get("Obj", [])
    return kline_data[::-1]  # 倒序（旧→新）


def get_vix_series(days: int = 20) -> list:
    """
    获取VIX恐慌指数走势

    Args:
        days: 获取天数

    Returns:
        VIX数据列表，每项包含 Date、High_VIX、Close_VIX
    """
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://{ALI_API_HOST}/query/comkm4?symbol=CBOEVIX&period=D&date={yesterday}"
    response = requests.get(url, headers=_get_ali_headers(), timeout=10)
    kline_data = response.json().get("Obj", [])
    kline_data = kline_data[-days:][::-1]

    processed = []
    for item in kline_data:
        original_date = item["D"]
        time_str = datetime.strptime(original_date, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        processed.append({
            "Date": time_str,
            "High_VIX": item["H"],
            "Close_VIX": item["C"],
        })
    return processed


def get_gld_assets_history(days: int = 20) -> Optional[list]:
    """
    从SSGA官网获取GLD黄金ETF的历史总资产数据

    Args:
        days: 获取天数

    Returns:
        资产数据列表，每项包含 date、total_net_assets
    """
    url = "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-gld.xlsx"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        xls = pd.ExcelFile(BytesIO(response.content))
        df = pd.read_excel(xls, sheet_name=0, skiprows=3)

        # 定位日期列和资产列
        date_col = None
        assets_col = None

        for col in df.columns:
            col_str = str(col).lower()
            if "date" in col_str:
                date_col = col
            elif "total net assets" in col_str or "net assets" in col_str:
                assets_col = col

        if not date_col:
            date_col = df.columns[0]
        if not assets_col:
            assets_col = df.columns[3]

        history_data = []
        for i in range(min(days, len(df))):
            date = df.iloc[i][date_col]
            assets = df.iloc[i][assets_col]

            # 解析日期
            if isinstance(date, pd.Timestamp):
                formatted_date = date.strftime("%Y-%m-%d")
            elif isinstance(date, datetime):
                formatted_date = date.strftime("%Y-%m-%d")
            else:
                for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
                    try:
                        formatted_date = datetime.strptime(str(date), fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                else:
                    formatted_date = str(date)

            # 解析资产值
            if isinstance(assets, str):
                assets_clean = assets.replace(",", "").replace("$", "")
                if "M" in assets_clean:
                    assets_value = float(assets_clean.replace("M", "")) * 1_000_000
                elif "B" in assets_clean:
                    assets_value = float(assets_clean.replace("B", "")) * 1_000_000_000
                else:
                    assets_value = float(assets_clean)
            else:
                assets_value = float(assets)

            history_data.append({
                "date": formatted_date,
                "total_net_assets": assets_value,
            })

        return history_data

    except Exception as e:
        print(f"获取GLD资产数据失败: {e}")
        return None


def get_merged_gold_data() -> dict:
    """
    获取并合并所有黄金相关数据

    Returns:
        合并后的数据字典，包含:
        - time: 当前时间
        - gold_price: 当前金价
        - gold_rsi_14: RSI指标
        - series: 合并后的历史数据列表
    """
    from .rsi_calculator import calculate_rsi, calculate_simple_rsi

    # 获取各数据源
    holdings_data = get_gld_holdings_history()
    vix_data = get_vix_series()
    gold_kline_data = get_gold_kline_data()
    today = china_now().strftime("%Y-%m-%d")
    raw_gold_kline_data = gold_kline_data
    gold_kline_data, _ = normalize_candles(gold_kline_data, today=today)

    fed_expectations = get_fed_expectations()
    try:
        xau_usd = get_xau_usd_price()
    except (requests.RequestException, ValueError, KeyError, TypeError):
        print("国际现货报价暂缺")
        xau_usd = None

    # 提取金价序列
    gold_data = []
    for item in gold_kline_data[-14:][::-1]:
        time_str = item["D"]
        gold_data.append({
            "Date": time_str,
            "gold_price": item["C"],
        })

    # 合并数据：以 GLD 持仓日期为权威骨架，金价/VIX 作为补充
    merged_data = {}
    for item in holdings_data:
        date = item["Date"]
        merged_data[date] = {
            "Date": date,
            "gold_tonnes": item["gold_tonnes"],
        }

    for item in gold_data:
        date = item["Date"]
        if date not in merged_data:
            merged_data[date] = {"Date": date}
        merged_data[date]["gold_price"] = item["gold_price"]

    for item in vix_data:
        date = item["Date"]
        if date in merged_data:
            merged_data[date].update({
                "High_VIX": item["High_VIX"],
                "Close_VIX": item["Close_VIX"],
            })

    # 转为列表并排序
    result = list(merged_data.values())
    result.sort(key=lambda x: x["Date"], reverse=False)

    # 按有效官方持仓记录比较，避免插入金价/VIX日期后丢失比较基准。
    result = [item for item in result if item["Date"] < today]
    previous_tonnes, previous_date = None, None
    for item in result:
        item["gold_tonnes_change"] = None
        current = positive_number(item.get("gold_tonnes"))
        if current is not None:
            if previous_tonnes is not None:
                item["gold_tonnes_change"] = round(current - previous_tonnes, 2)
                item["gold_tonnes_baseline_date"] = previous_date
            previous_tonnes, previous_date = current, item["Date"]

    # 按日期降序
    result.sort(key=lambda x: x["Date"], reverse=True)

    # 计算RSI
    gold_rsi = calculate_rsi([item["C"] for item in gold_kline_data]) if gold_kline_data else None
    simple_rsi = calculate_simple_rsi([item["C"] for item in gold_kline_data]) if gold_kline_data else None
    gold_price = get_gold_price_now()

    return {
        "time": china_now().strftime("%Y-%m-%d %H:%M"),
        "gold_price": gold_price,
        "price_summary": build_price_summary(raw_gold_kline_data, gold_price, today=today),
        "holdings_summary": build_holdings_summary(holdings_data, today=today),
        "xau_usd": xau_usd,
        "fed_expectations": fed_expectations,
        "gold_holdings_source": "SPDR官方公布实物持仓（吨），按各记录日期使用；缺失不估算",
        "gold_rsi_14": gold_rsi,
        "simple_rsi_14": simple_rsi,
        "ali_rsi_14": get_ali_rsi(),
        "series": result,
    }


def get_ali_rsi() -> Optional[float]:
    """
    从阿里云 /query/indicator 拉 SGEAU9999 RSI(14)

    Returns:
        RSI 数值（float）；接口失败时返回 None
    """
    args_str = urllib.parse.quote(
        json.dumps({"lookbackPeriod": "14"}, separators=(",", ":"))
    )
    url = f"https://{ALI_API_HOST}/query/indicator"
    params = {
        "symbol": "SGEAU9999",
        "period": "D",
        "indkey": "Rsi",
        "outputcount": "1",
        "args": args_str,
    }
    try:
        response = requests.get(url, headers=_get_ali_headers(), params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            return float(data[0].get("Rsi"))
        return None
    except Exception as e:
        print(f"获取阿里云 RSI 失败: {e}")
        return None
