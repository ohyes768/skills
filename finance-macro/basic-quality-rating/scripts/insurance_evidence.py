"""Locate unaccepted insurance metric candidates in an existing PDF cache.

Confirm listed group versus legal insurer, dates, units and table columns before
creating insurance-data. No download, parsing, OCR or source certification here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from metric_candidates import find_metric_candidates
from pdf_evidence import DEFAULT_MAX_CHARS

METRIC_LABELS = {
    "roe": ("加权平均净资产收益率", "加权平均净资产回报率"),
    "group_solvency_ratio": (
        "集团综合偿付能力充足率",
        "保险集团综合偿付能力充足率",
        "集团偿付能力充足率",
    ),
    "core_solvency": ("核心偿付能力充足率",),
    "comprehensive_solvency": ("综合偿付能力充足率",),
    "nbv": ("新业务价值", "NBV"),
    "new_business_csm": ("新业务合同服务边际", "新业务CSM"),
    "csm_balance": ("合同服务边际余额", "合同服务边际", "CSM余额"),
    "combined_ratio": ("综合成本率", "综合成本比率"),
    "net_investment_yield": ("净投资收益率",),
    "comprehensive_investment_yield": ("综合投资收益率",),
    "total_investment_yield": ("总投资收益率",),
    "reserves": ("保险合同准备金", "保险责任准备金", "赔款准备金", "准备金"),
    "surrender_ratio": ("退保率",),
    "continuation_ratio": ("13个月保单继续率", "25个月保单继续率", "保单继续率", "继续率"),
}
_CONFIRMATION = (
    "候选值未入分：必须核对年份列、金额/百分比单位、上市集团与保险法人主体及指标定义；"
    "偿付能力不可跨主体平均，NBV/CSM不是监管资本指标，不自动选择数字或认证来源。"
)


def find_insurance_candidates(
    document_dir: Path | str, *, max_chars=DEFAULT_MAX_CHARS, cursor=None
) -> dict:
    return find_metric_candidates(
        document_dir,
        METRIC_LABELS,
        selection_id="insurance-candidates-v1",
        confirmation=_CONFIRMATION,
        search_scope="First matched insurance metric on each indexed PDF page; no OCR",
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
        result = find_insurance_candidates(
            args.document_dir, max_chars=args.max_chars, cursor=args.cursor
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        print(f"insurance_evidence: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
