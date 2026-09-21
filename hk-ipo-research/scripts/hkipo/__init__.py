"""hkipo - Hong Kong IPO research tools using active public sources."""

from .tradesmart import (
    fetch_tracker_margin_records,
    fetch_tradesmart_ipos,
    get_entry_amount,
    get_tracker_ipo,
    get_tracker_margin,
    get_tradesmart_ipo,
)
from .allotment import predict_allotment, predict_allotment_table
from .jisilu import fetch_jisilu_history, get_jisilu_stock
from .etnet import fetch_sponsor_rankings, get_sponsor_stats
from .hkex import fetch_hkex_active_ipos, fetch_hkex_active_ipos_sync, get_prospectus_url

__version__ = "3.0.0"
__all__ = [
    "fetch_tracker_margin_records",
    "fetch_tradesmart_ipos",
    "get_entry_amount",
    "get_tracker_ipo",
    "get_tracker_margin",
    "get_tradesmart_ipo",
    "predict_allotment",
    "predict_allotment_table",
    "fetch_jisilu_history",
    "get_jisilu_stock",
    "fetch_sponsor_rankings",
    "get_sponsor_stats",
    "fetch_hkex_active_ipos",
    "fetch_hkex_active_ipos_sync",
    "get_prospectus_url",
]
