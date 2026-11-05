"""报告显示值解析：百分号、金额单位及显示精度均参与数值匹配。

数字 token 分型：金额/比率按单位缩放匹配；方向词（下降/亏损）建模符号；
「个百分点」按比率×100 匹配；年份+期间后缀为非财务 token。
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

NUMBER_RE = re.compile(
    r"(?<![\d.])(?P<number>[+-]?\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>亿元|万元|千元|亿|万|元|yuan|[%％])?(?![A-Za-z])", re.IGNORECASE
)
SCALES = {"亿元": Decimal("1e8"), "亿": Decimal("1e8"),
          "万元": Decimal("1e4"), "万": Decimal("1e4"),
          "千元": Decimal("1e3"), "元": Decimal(1), "yuan": Decimal(1),
          "%": Decimal("0.01"), "％": Decimal("0.01")}

_DECLINE_RE = re.compile(r"(?:下降|下跌|下滑|回落|减少|降幅|亏损)[为达约]?\s*$")
_PERIOD_SUFFIX_RE = re.compile(
    r"\s*(?:年|年上半年|年下半年|上半年|下半年|Q[1-4]|H[1-2]|第[一二三四]季度)", re.IGNORECASE
)
_PERCENT_POINT_SUFFIX_RE = re.compile(r"\s*个?\s*(?:百分点|pct|pp)(?![a-z])", re.IGNORECASE)


def matches_number(match, value: Decimal, display_unit: str | None = None,
                   value_kind: str | None = None, direction: str | None = None) -> bool:
    if direction == "decline":
        if value > 0:
            return False
        if value < 0:
            value = -value
    raw = Decimal(match.group("number").replace(",", ""))
    unit = match.group("unit") or display_unit
    if value_kind == "amount" and unit in ("%", "％"):
        return False
    if value_kind == "ratio" and unit and unit not in ("%", "％"):
        return False
    scale = SCALES.get((unit or "").lower(), Decimal(1))
    number = raw * scale
    if not value.is_finite():
        return False
    if number == value:
        return True
    if not unit and raw.as_tuple().exponent >= 0 and value % 1:
        return False
    quantum = Decimal(1).scaleb(raw.as_tuple().exponent) * scale
    try:
        return value.quantize(quantum, rounding=ROUND_HALF_UP) == number
    except InvalidOperation:
        return False


def decline_context(text: str, match) -> bool:
    prefix = text[max(0, match.start() - 8):match.start()]
    return bool(_DECLINE_RE.search(prefix))


def period_year_suffix(text: str, match) -> bool:
    suffix = text[match.end():match.end() + 8]
    return bool(_PERIOD_SUFFIX_RE.match(suffix))


def percentage_point_suffix(text: str, match) -> bool:
    suffix = text[match.end():match.end() + 8]
    return bool(_PERCENT_POINT_SUFFIX_RE.match(suffix))


def text_contains_value(text: str, value: Decimal, display_unit: str | None = None,
                        value_kind: str | None = None) -> bool:
    return any(matches_number(match, value, display_unit, value_kind,
                              direction="decline" if decline_context(text, match) else None)
               for match in NUMBER_RE.finditer(text))


def plain_text(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", "", text)
