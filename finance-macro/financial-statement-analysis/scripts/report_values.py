"""报告显示值解析：百分号、金额单位及显示精度均参与数值匹配。"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

NUMBER_RE = re.compile(
    r"(?<![\d.])(?P<number>[+-]?\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>亿元|万元|千元|亿|万|元|yuan|[%％])?", re.IGNORECASE
)
SCALES = {"亿元": Decimal("1e8"), "亿": Decimal("1e8"),
          "万元": Decimal("1e4"), "万": Decimal("1e4"),
          "千元": Decimal("1e3"), "元": Decimal(1), "yuan": Decimal(1),
          "%": Decimal("0.01"), "％": Decimal("0.01")}


def matches_number(match, value: Decimal, display_unit: str | None = None,
                   value_kind: str | None = None) -> bool:
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


def text_contains_value(text: str, value: Decimal, display_unit: str | None = None,
                        value_kind: str | None = None) -> bool:
    return any(matches_number(match, value, display_unit, value_kind)
               for match in NUMBER_RE.finditer(text))


def plain_text(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", "", text)
