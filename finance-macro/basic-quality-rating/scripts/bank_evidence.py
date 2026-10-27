"""Locate bank metric candidates in an existing, integrity-checked PDF cache.

Candidates preserve raw text and numeric strings. They are NOT accepted values:
confirm table columns, dates, units, group scope and source before bank scoring.
No downloading, PDF parsing, OCR or source authenticity certification occurs here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from metric_candidates import find_metric_candidates
from pdf_evidence import DEFAULT_MAX_CHARS

# Longer aliases precede contained labels in one regex, so a core-tier-1 label
# does not also create tier-1 and total-capital candidates at the same position.
METRIC_LABELS = {
    "roe": ("加权平均净资产收益率", "加权平均净资产回报率"),
    "roa": ("平均总资产收益率", "平均总资产回报率", "总资产收益率"),
    "npl_ratio": ("不良贷款率",),
    "provision_coverage": ("拨备覆盖率",),
    "loan_provision_ratio": ("贷款拨备率", "拨贷比"),
    "cet1_ratio": ("核心一级资本充足率",),
    "tier1_ratio": ("一级资本充足率",),
    "total_capital_ratio": ("资本充足率",),
    "lcr": ("流动性覆盖率",),
    "nsfr": ("净稳定资金比例",),
    "nim": ("净息差",),
    "cost_income_ratio": ("成本收入比", "成本收入比例"),
    "special_mention_ratio": ("关注类贷款占比", "关注类贷款比例", "关注类贷款"),
    "overdue_90_ratio": (
        "逾期90天以上贷款占比",
        "逾期90天以上贷款",
        "逾期90天贷款",
    ),
}
_CONFIRMATION = (
    "候选值未入分：必须核对表格列对应的年份、单位、集团/母行口径及指标定义；"
    "相邻数字可能属于其他指标或比较期间，不自动选择列、换算百分比或认证来源。"
)


def find_bank_candidates(
    document_dir: Path | str, *, max_chars=DEFAULT_MAX_CHARS, cursor=None
) -> dict:
    """Return first occurrence per metric/PDF page, with bounded continuation.

    Reuse pdf_evidence's cache verification and packet/cursor implementation so
    replacement/corruption of any bound source invalidates old continuations.
    Whitespace inside labels is tolerated, including labels split across lines.
    """
    return find_metric_candidates(
        document_dir,
        METRIC_LABELS,
        selection_id="bank-candidates-v1",
        confirmation=_CONFIRMATION,
        search_scope="First matched bank metric on each indexed PDF page; no OCR",
        max_chars=max_chars,
        cursor=cursor,
    )


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-dir", required=True)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--cursor")
    args = parser.parse_args(argv)
    try:
        result = find_bank_candidates(
            args.document_dir, max_chars=args.max_chars, cursor=args.cursor
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        print(f"bank_evidence: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
