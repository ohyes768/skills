"""Offline whitelist arithmetic, not a validator of investment assumptions.

Inputs: decimal strings or finite Python int/float/Decimal (never bool).
Bounds are resource guards, not financial rules: <=128 characters, <=64 digits,
absolute exponent/adjusted exponent <=100, and 1..100 annual cash flows.
Evaluation retains unrounded precision; published prices round HALF_UP to cents.
"""
import re
from decimal import ROUND_HALF_UP, Context, Decimal, DecimalException, localcontext

CONTEXT = Context(prec=256, rounding=ROUND_HALF_UP, Emin=-20000, Emax=20000)
METHODS = ("pe_multiple", "pb_multiple", "equity_cashflow_pv")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def decimal_value(value, label="number") -> Decimal:
    """Parse bounded finite numeric data without evaluating expressions."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{label}: expected a decimal number, not bool/null")  # noqa: TRY004 - CLI contract maps every failure to ValueError
    text = str(value)
    if len(text) > 128 or not NUMBER.fullmatch(text):
        raise ValueError(f"{label}: invalid or overlong decimal")
    try:
        number = Decimal(text)
    except DecimalException as exc:
        raise ValueError(f"{label}: invalid decimal") from exc
    if not number.is_finite():
        raise ValueError(f"{label}: number must be finite")
    parts = number.as_tuple()
    if len(parts.digits) > 64 or abs(parts.exponent) > 100 or abs(number.adjusted()) > 100:
        raise ValueError(f"{label}: numeric resource bound exceeded")
    return number


def exact_keys(value, required, optional=(), label="object"):
    """Reject missing/unknown keys before accessing an untrusted mapping."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label}: expected object with string keys")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise ValueError(f"{label}: missing={sorted(missing)}, unknown={sorted(unknown)}")


def _positive(value, label):
    number = decimal_value(value, label)
    if number <= 0:
        raise ValueError(f"{label}: must be positive")
    return number


def _terminal(node, rate, finite_life):
    if not isinstance(node, dict):
        raise ValueError("terminal: expected object")  # noqa: TRY004 - contract uses ValueError
    kind = node.get("kind")
    if kind == "value":
        exact_keys(node, ("kind", "value"), label="terminal")
        value = decimal_value(node["value"], "terminal.value")
        if value < 0:
            raise ValueError("terminal.value: must be nonnegative")
        return value
    if kind == "exit_pe":
        exact_keys(node, ("kind", "eps", "multiple"), label="terminal")
        return _positive(node["eps"], "terminal.eps") * _positive(node["multiple"], "terminal.multiple")
    if kind == "perpetuity":
        exact_keys(node, ("kind", "next_cashflow", "growth"), label="terminal")
        if finite_life:
            raise ValueError("finite_life: perpetuity is prohibited")
        growth = decimal_value(node["growth"], "terminal.growth")
        if not -1 < growth < rate:
            raise ValueError("terminal.growth: must be >-1 and <discount_rate")
        return _positive(node["next_cashflow"], "terminal.next_cashflow") / (rate - growth)
    raise ValueError("terminal.kind: unsupported")


def _evaluate(node):
    if not isinstance(node, dict):
        raise ValueError("model: expected object")  # noqa: TRY004 - contract uses ValueError
    method = node.get("method")
    if method == "pe_multiple":
        exact_keys(node, ("method", "eps", "multiple"), ("margin",), "model")
        value = _positive(node["eps"], "eps") * _positive(node["multiple"], "multiple")
    elif method == "pb_multiple":
        exact_keys(node, ("method", "bvps", "multiple"), ("margin",), "model")
        value = _positive(node["bvps"], "bvps") * _positive(node["multiple"], "multiple")
    elif method == "equity_cashflow_pv":
        exact_keys(node, ("method", "cashflows", "discount_rate", "cashflow_basis", "finite_life", "terminal"), ("margin",), "model")
        if node["cashflow_basis"] not in ("dividend", "fcfe"):
            raise ValueError("cashflow_basis: dividend or fcfe required")
        if type(node["finite_life"]) is not bool:
            raise ValueError("finite_life: explicit boolean required")
        flows = node["cashflows"]
        if not isinstance(flows, list) or not 1 <= len(flows) <= 100:
            raise ValueError("cashflows: expected 1..100 year-end values")
        rate = _positive(node["discount_rate"], "discount_rate")
        value = sum((decimal_value(flow, f"cashflows[{i}]") / (1 + rate) ** i
                     for i, flow in enumerate(flows, 1)), Decimal(0))
        value += _terminal(node["terminal"], rate, node["finite_life"]) / (1 + rate) ** len(flows)
    else:
        raise ValueError("method: unsupported; arbitrary expressions are prohibited")
    margin = decimal_value(node.get("margin", "0"), "margin")
    if not 0 <= margin < 1:
        raise ValueError("margin: must be >=0 and <1")
    value *= 1 - margin
    if not value.is_finite() or value <= 0:
        raise ValueError("model: final present value must be finite and positive")
    return value


def evaluate(node) -> Decimal:
    """Return unrounded present equity value using a private Decimal context."""
    try:
        with localcontext(CONTEXT):
            return _evaluate(node)
    except DecimalException as exc:
        raise ValueError("model: decimal arithmetic bound exceeded") from exc


def round_price(value) -> Decimal:
    """Round to cents; a value that rounds to zero is not a valid price."""
    try:
        with localcontext(CONTEXT):
            number = value if isinstance(value, Decimal) else decimal_value(value, "price")
            if not number.is_finite() or number <= 0:
                raise ValueError("price: must be finite and positive")
            rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if rounded <= 0:
                raise ValueError("price: rounds to zero")
            return rounded
    except DecimalException as exc:
        raise ValueError("price: decimal arithmetic bound exceeded") from exc


def level_metrics(price, ttm_eps, common_bvps, annual_dps):
    """Ratios use rounded price, TTM EPS, ordinary BVPS and percentage DPS yield."""
    with localcontext(CONTEXT):
        price = round_price(price)
        values = [None if value is None else decimal_value(value, label)
                  for value, label in [(ttm_eps, "ttm_eps"), (common_bvps, "common_bvps"), (annual_dps, "annual_dps")]]
        eps, bvps, dps = values
        if dps is not None and dps < 0:
            raise ValueError("annual_dps: must be nonnegative")
        quantum = Decimal("0.0001")
        rounding = {"rounding": ROUND_HALF_UP}
        return {
            "pe": (price / eps).quantize(quantum, **rounding) if eps is not None and eps > 0 else None,
            "pb": (price / bvps).quantize(quantum, **rounding) if bvps is not None and bvps > 0 else None,
            "dividend_yield_pct": (dps / price * 100).quantize(quantum, **rounding) if dps is not None else None,
        }
