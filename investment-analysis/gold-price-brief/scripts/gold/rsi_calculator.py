"""
RSI 技术指标计算模块
"""

import numpy as np
from typing import Optional


def calculate_rsi(prices: list, period: int = 14) -> Optional[float]:
    """
    计算RSI相对强弱指数（Wilder EMA平滑方式）

    Args:
        prices: 价格列表（收盘价）
        period: RSI周期，默认14

    Returns:
        RSI值，如果数据不足返回None
    """
    if len(prices) <= period:
        return None

    prices = np.array(prices)
    deltas = np.diff(prices)

    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period

    for i in range(period, len(deltas)):
        delta = deltas[i]
        if delta > 0:
            up_val = delta
            down_val = 0
        else:
            up_val = 0
            down_val = -delta

        up = (up * (period - 1) + up_val) / period
        down = (down * (period - 1) + down_val) / period
    if down == 0:
        return 100.0 if up > 0 else 50.0
    return round(float(100 - 100 / (1 + up / down)), 2)


def calculate_simple_rsi(prices: list, period: int = 14) -> Optional[float]:
    """
    计算简单RSI（纯14天窗口，不含EMA惯性）

    Args:
        prices: 价格列表（收盘价）
        period: RSI周期，默认14

    Returns:
        RSI值，如果数据不足返回None
    """
    if len(prices) <= period:
        return None

    prices = np.array(prices)
    deltas = np.diff(prices)
    window = deltas[-period:]

    up_avg = window[window >= 0].sum() / period
    down_avg = -window[window < 0].sum() / period

    if down_avg == 0:
        return 100.0 if up_avg > 0 else 50.0

    rs = up_avg / down_avg
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)
