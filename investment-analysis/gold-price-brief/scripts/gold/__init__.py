"""
黄金分析推送模块
"""

from .data_fetcher import (
    get_gold_price_now,
    get_xau_usd_price,
    get_gold_kline_data,
    get_vix_series,
    get_gld_assets_history,
    get_merged_gold_data,
    get_ali_rsi,
)
from .rsi_calculator import calculate_rsi, calculate_simple_rsi
from .analyzer import GoldAnalyzer

__all__ = [
    "get_gold_price_now",
    "get_gold_kline_data",
    "get_vix_series",
    "get_gld_assets_history",
    "get_merged_gold_data",
    "get_ali_rsi",
    "calculate_rsi",
    "calculate_simple_rsi",
    "GoldAnalyzer",
]
