from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

CENT = Decimal("0.01")


def decimal_value(value, *, positive=False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid decimal value") from exc
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise ValueError("Value must be finite and non-negative (positive when required)")
    if len(number.as_tuple().digits) > 28 or number.adjusted() > 18 or number.as_tuple().exponent < -8:
        raise ValueError("Unsupported decimal precision or scale")
    return number


def money(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
