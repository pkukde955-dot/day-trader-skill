"""Paper-only isolated USDT perpetual engine; contains no live exchange methods."""
import copy, json, os, threading, time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN


class PaperPerpsError(Exception):
    pass


def dec(value, field="value"):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PaperPerpsError("Invalid " + field) from exc
    if not result.is_finite():
        raise PaperPerpsError("Non-finite " + field)
    return result


class PerpsPaperTrader:
    VERSION = 1

    def __init__(self, starting_balance="1000", fee_rate="0.0005",
                 slippage_rate="0.0005", daily_loss_limit="20",
                 max_leverage="10", max_margin_fraction="0.20",
                 maintenance_margin_rate="0.005", journal_path=None):
        self._lock = threading.RLock()
        self.balance = dec(starting_balance)
        self.fee_rate, self.slippage_rate = dec(fee_rate), dec(slippage_rate)
        self.daily_loss_limit, self.max_leverage = dec(daily_loss_limit), dec(max_leverage)
        self.max_margin_fraction = dec(max_margin_fraction)
        self.maintenance_margin_rate = dec(maintenance_margin_rate)
        if self.balance <= 0 or self.daily_loss_limit <= 0:
            raise ValueError("Balance and daily loss limit must be positive")
        if not (0 <= self.fee_rate < 1 and 0 <= self.slippage_rate < 1):
            raise ValueError("Fee and slippage rates must be in [0, 1)")
        if self.max_leverage < 1 or not (0 < self.max_margin_fraction <= 1):
            raise ValueError("Invalid leverage or margin fraction")
        if not (0 <= self.maintenance_margin_rate < 1):
            raise ValueError("Invalid maintenance margin rate")
        self.journal_path = journal_path
        self.positions, self.marks, self.seen_ids, self.funding_events = {}, {}, set(), set()
        self.daily_realized, self.daily_key = Decimal("0"), None
        self._restore()

    def _day(self, ts):
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()

    def _roll_day(self, ts):
        key = self._day(ts)
        if key != self.daily_key:
            self.daily_key, self.daily_realized = key, Decimal("0")

    def _qty(self, quantity, step):
        quantity, step = dec(quantity), dec(step)
        if quantity <= 0 or step <= 0:
            raise PaperPerpsError("Quantity and step must be positive")
        return (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step

    def _unrealized(self):
        total = Decimal("0")
        for symbol, p in self.positions.items():
            if symbol in self.marks:
                sign = Decimal("1") if p["side"] == "LONG" else Decimal("-1")
                total += sign * (self.marks[symbol] - p["entry"]) * p["qty"]
        return total

    def _used_margin(self):
        return sum((p["margin"] for p in self.positions.values()), Decimal("0"))

    def _equity(self):
        return self.balance + self._used_margin() + self._unrealized()

    def _snapshot(self):
        return copy.deepcopy((self.balance, self.positions, self.seen_ids,
                              self.daily_realized, self.daily_key, self.funding_events))

    def _state(self):
        return {"version": self.VERSION, "balance": str(self.balance),
                "positions": {s: {k: str(v) for k, v in p.items()} for s, p in self.positions.items()},
                "seen_ids": sorted(self.seen_ids), "daily_realized": str(self.daily_realized),
                "daily_key": self.daily_key, "funding_events": sorted(self.funding_events)}

    def _persist(self):
        if not self.journal_path:
            return
        parent = os.path.dirname(self.journal_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "state", "state": self._state()}, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _commit(self, before):
        try:
            self._persist()
        except Exception:
            (self.balance, self.positions, self.seen_ids, self.daily_realized,
             self.daily_key, self.funding_events) = before
            raise

    def _restore(self):
        if not self.journal_path or not os.path.exists(self.journal_path):
            return
        with open(self.journal_path, encoding="utf-8") as f:
            lines = f.readlines()
        if lines and not lines[-1].endswith("\n"):
            lines = lines[:-1]
            with open(self.journal_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        last = None
        for n, line in enumerate(lines, 1):
            try:
                state = json.loads(line)["state"]
                if state["version"] != self.VERSION:
                    raise ValueError("Unsupported journal version")
                balance = dec(state["balance"])
                positions = {}
                for symbol, p in state["positions"].items():
                    side = p["side"]
                    vals = {k: dec(p[k]) for k in
                            ("qty", "entry", "leverage", "margin", "maintenance_rate", "funding_paid")}
                    if side not in ("LONG", "SHORT") or min(vals[k] for k in ("qty", "entry", "leverage", "margin")) <= 0:
                        raise ValueError("Invalid position")
                    positions[symbol] = dict(vals, side=side)
                ids = state["seen_ids"]
                if len(ids) != len(set(ids)) or not all(isinstance(x, str) and x for x in ids):
                    raise ValueError("Invalid signal IDs")
                last = (balance, positions, set(ids), dec(state["daily_realized"]),
                        state["daily_key"], set(state["funding_events"]))
            except Exception as exc:
                raise PaperPerpsError("Journal recovery failed at line %d: %s" % (n, exc)) from exc
        if last:
            (self.balance, self.positions, self.seen_ids, self.daily_realized,
             self.daily_key, self.funding_events) = last

    def update_marks(self, marks, timestamp_ms=None):
        with self._lock:
            if not isinstance(marks, dict) or not marks:
                raise PaperPerpsError("Non-empty mark snapshot required")
            clean = {}
            for symbol, value in marks.items():
                if not (isinstance(symbol, str) and symbol.startswith("B-") and symbol.endswith("_USDT")):
                    raise PaperPerpsError("Only B-*_USDT perpetual symbols supported")
                price = dec(value, "mark price")
                if price <= 0:
                    raise PaperPerpsError("Mark price must be positive")
                clean[symbol] = price
            self.marks = clean
            self._roll_day(timestamp_ms or int(time.time() * 1000))
            return self.status(timestamp_ms)

    def _risk_check(self, ts):
        self._roll_day(ts)
        if self.daily_realized + self._unrealized() <= -self.daily_loss_limit:
            raise PaperPerpsError("Daily loss limit reached; new positions blocked")

    def open_position(self, symbol, side, reference_price, quantity, leverage, signal_id,
                      quantity_step="0.001", min_quantity="0.001",
                      maintenance_margin_rate=None, timestamp_ms=None):
        with self._lock:
            ts = timestamp_ms or int(time.time() * 1000)
            self._risk_check(ts)
            if side not in ("LONG", "SHORT"):
                raise PaperPerpsError("side must be LONG or SHORT")
            if not (isinstance(symbol, str) and symbol.startswith("B-") and symbol.endswith("_USDT")):
                raise PaperPerpsError("Only USDT perpetual symbols supported")
            if symbol in self.positions:
                raise PaperPerpsError("Close existing position before reversing")
            if not isinstance(signal_id, str) or not signal_id.strip() or signal_id in self.seen_ids:
                raise PaperPerpsError("Missing or duplicate signal_id")
            price, lev = dec(reference_price), dec(leverage)
            qty = self._qty(quantity, quantity_step)
            if price <= 0 or qty < dec(min_quantity):
                raise PaperPerpsError("Invalid price or quantity below minimum")
            if lev < 1 or lev > self.max_leverage:
                raise PaperPerpsError("Leverage outside configured limit")
            fill = price * (1 + self.slippage_rate if side == "LONG" else 1 - self.slippage_rate)
            notional, margin = fill * qty, fill * qty / lev
            fee = notional * self.fee_rate
            if margin > self._equity() * self.max_margin_fraction:
                raise PaperPerpsError("Initial margin exceeds configured equity fraction")
            if margin + fee > self.balance:
                raise PaperPerpsError("Insufficient available balance")
            mmr = self.maintenance_margin_rate if maintenance_margin_rate is None else dec(maintenance_margin_rate)
            if not (0 <= mmr < 1):
                raise PaperPerpsError("Invalid maintenance margin rate")
            before = self._snapshot()
            self.balance -= margin + fee
            self.daily_realized -= fee
            self.daily_key = self._day(ts)
            self.positions[symbol] = {"side": side, "qty": qty, "entry": fill,
                "leverage": lev, "margin": margin, "maintenance_rate": mmr,
                "funding_paid": Decimal("0")}
            self.seen_ids.add(signal_id)
            self._commit(before)
            return {"symbol": symbol, "side": side, "quantity": qty, "fill_price": fill,
                    "notional": notional, "leverage": lev, "initial_margin": margin,
                    "entry_fee": fee, "estimated_liquidation_price": self.liquidation_estimate(symbol),
                    "liquidation_estimate_note": "Simplified isolated-margin estimate; excludes tiered maintenance, close fees and exchange liquidation rules."}

    def liquidation_estimate(self, symbol):
        p = self.positions[symbol]
        rate = p["maintenance_rate"]
        if p["side"] == "LONG":
            return p["entry"] * (1 - 1 / p["leverage"]) / (1 - rate)
        return p["entry"] * (1 + 1 / p["leverage"]) / (1 + rate)

    def close_position(self, symbol, reference_price, signal_id, timestamp_ms=None):
        with self._lock:
            if symbol not in self.positions:
                raise PaperPerpsError("No open position")
            if not isinstance(signal_id, str) or not signal_id.strip() or signal_id in self.seen_ids:
                raise PaperPerpsError("Missing or duplicate signal_id")
            p, ref = self.positions[symbol], dec(reference_price)
            if ref <= 0:
                raise PaperPerpsError("Close price must be positive")
            sign = Decimal("1") if p["side"] == "LONG" else Decimal("-1")
            fill = ref * (1 - self.slippage_rate if p["side"] == "LONG" else 1 + self.slippage_rate)
            pnl, fee = sign * (fill - p["entry"]) * p["qty"], fill * p["qty"] * self.fee_rate
            net = pnl - fee
            ts = timestamp_ms or int(time.time() * 1000)
            before = self._snapshot()
            self.balance += p["margin"] + pnl - fee
            self.daily_realized = (self.daily_realized if self.daily_key == self._day(ts) else Decimal("0")) + net
            self.daily_key = self._day(ts)
            del self.positions[symbol]
            self.seen_ids.add(signal_id)
            self._commit(before)
            return {"symbol": symbol, "side": p["side"], "quantity": p["qty"],
                    "fill_price": fill, "gross_pnl": pnl, "exit_fee": fee,
                    "net_pnl": net, "balance": self.balance}

    def apply_funding(self, symbol, funding_rate, event_id, mark_price=None, timestamp_ms=None):
        with self._lock:
            if symbol not in self.positions:
                raise PaperPerpsError("No open position for funding")
            if not isinstance(event_id, str) or not event_id.strip() or event_id in self.funding_events:
                raise PaperPerpsError("Missing or duplicate funding event")
            p = self.positions[symbol]
            mark = dec(mark_price if mark_price is not None else self.marks.get(symbol), "funding mark")
            rate = dec(funding_rate, "funding rate")
            if mark <= 0:
                raise PaperPerpsError("Funding mark must be positive")
            sign = Decimal("1") if p["side"] == "LONG" else Decimal("-1")
            payment = -sign * mark * p["qty"] * rate
            before = self._snapshot()
            self.balance += payment
            ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
            self._roll_day(ts)
            self.daily_realized += payment
            p["funding_paid"] += -payment
            self.funding_events.add(event_id)
            self._commit(before)
            return {"symbol": symbol, "funding_payment": payment,
                    "meaning": "paid" if payment < 0 else "received",
                    "cumulative_funding_paid": p["funding_paid"]}

    def status(self, timestamp_ms=None):
        with self._lock:
            self._roll_day(timestamp_ms or int(time.time() * 1000))
            unreal = self._unrealized()
            return {"mode": "PAPER", "live_trading_enabled": False,
                "wallet_balance": self.balance, "used_margin": self._used_margin(),
                "available_balance": self.balance, "unrealized_pnl": unreal,
                "equity": self._equity(), "daily_realized_pnl": self.daily_realized,
                "daily_risk_pnl": self.daily_realized + unreal,
                "daily_loss_limit": self.daily_loss_limit,
                "positions": copy.deepcopy(self.positions), "open_position_count": len(self.positions),
                "marks": dict(self.marks)}
