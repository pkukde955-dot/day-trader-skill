"""Risk-checked NSE/BSE F&O order intent builder.

This module prepares an order plan only. It does not fetch market data or send
orders. Live execution belongs in a broker adapter after its official API and
contract specifications are verified.
"""
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


class OrderIntentError(ValueError):
    """Raised when a proposed order is incomplete or unsafe."""


def _positive_decimal(name, value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise OrderIntentError("{} must be a number".format(name))
    if not number.is_finite() or number <= 0:
        raise OrderIntentError("{} must be a finite positive number".format(name))
    return number


def build_order_intent(*, symbol, exchange, side, entry, stop, target,
                       risk_budget, lot_size=1, max_lots=None):
    """Build a deterministic, risk-sized manual-confirmation order intent.

    Prices and risk budget must be supplied by the caller; this function does
    not claim they are live or verified. Quantity is rounded down to whole lots.
    """
    symbol = str(symbol or "").strip().upper()
    exchange = str(exchange or "").strip().upper()
    side = str(side or "").strip().upper()
    if not symbol:
        raise OrderIntentError("symbol is required")
    if exchange not in ("NSE", "BSE"):
        raise OrderIntentError("exchange must be NSE or BSE")
    if side not in ("BUY", "SELL"):
        raise OrderIntentError("side must be BUY or SELL")

    entry = _positive_decimal("entry", entry)
    stop = _positive_decimal("stop", stop)
    target = _positive_decimal("target", target)
    risk_budget = _positive_decimal("risk_budget", risk_budget)
    lot_decimal = _positive_decimal("lot_size", lot_size)
    if lot_decimal != lot_decimal.to_integral_value():
        raise OrderIntentError("lot_size must be a whole number")
    lot_size = int(lot_decimal)

    if side == "BUY" and not stop < entry < target:
        raise OrderIntentError("BUY requires stop < entry < target")
    if side == "SELL" and not target < entry < stop:
        raise OrderIntentError("SELL requires target < entry < stop")

    risk_per_unit = abs(entry - stop)
    reward_per_unit = abs(target - entry)
    raw_units = (risk_budget / risk_per_unit).to_integral_value(rounding=ROUND_FLOOR)
    lots = int(raw_units // lot_size)
    if max_lots is not None:
        try:
            cap = int(max_lots)
        except (TypeError, ValueError):
            raise OrderIntentError("max_lots must be a positive whole number")
        if str(cap) != str(max_lots).strip() or cap <= 0:
            raise OrderIntentError("max_lots must be a positive whole number")
        lots = min(lots, cap)
    if lots < 1:
        raise OrderIntentError("risk budget is too small for one full lot")

    quantity = lots * lot_size
    planned_risk = risk_per_unit * quantity
    planned_reward = reward_per_unit * quantity
    rr = reward_per_unit / risk_per_unit
    return {
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "order_type": "LIMIT",
        "entry_reference": str(entry),
        "stop_loss_reference": str(stop),
        "target_reference": str(target),
        "lot_size": lot_size,
        "lots": lots,
        "quantity": quantity,
        "risk_budget": str(risk_budget),
        "planned_risk": str(planned_risk),
        "planned_reward": str(planned_reward),
        "reward_risk_ratio": str(rr.quantize(Decimal("0.01"))),
        "market_data_verified": False,
        "broker_connected": False,
        "order_placed": False,
        "status": "AWAITING_USER_REVIEW",
        "notice": (
            "Prices are caller-supplied references, not verified live quotes. "
            "No order was sent. Contract lot size, tick size, margin, charges, "
            "slippage and broker API support must be checked before execution."
        ),
    }
