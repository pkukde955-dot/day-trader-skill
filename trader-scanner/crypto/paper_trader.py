"""Spot-only crypto paper trader. Never sends exchange orders."""

import copy
import json
import os
import time
import threading
from functools import wraps
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN


def _synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


class PaperTradeError(Exception):
    pass


def D(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PaperTradeError("Invalid decimal value")
    if not result.is_finite():
        raise PaperTradeError("Non-finite decimal value")
    return result


class PaperTrader:
    VERSION = 1

    def __init__(
        self,
        starting_cash="1000",
        fee_rate="0.001",
        slippage_rate="0.001",
        qty_step="0.001",
        min_qty="0.001",
        daily_loss_limit="20",
        max_open_exposure=None,
        journal_path="data/crypto_paper_journal.jsonl",
    ):
        self._lock = threading.RLock()
        self.fee_rate = D(fee_rate)
        self.slippage_rate = D(slippage_rate)
        self.qty_step = D(qty_step)
        self.min_qty = D(min_qty)
        self.daily_loss_limit = D(daily_loss_limit)
        self.journal_path = journal_path

        if not (0 <= self.fee_rate < 1):
            raise ValueError("fee_rate must be >= 0 and < 1")
        if not (0 <= self.slippage_rate < 1):
            raise ValueError("slippage_rate must be >= 0 and < 1")
        if self.qty_step <= 0 or self.min_qty <= 0:
            raise ValueError("Quantity step and minimum must be positive")
        if self.daily_loss_limit <= 0:
            raise ValueError("Daily loss limit must be positive")

        self.cash = D(starting_cash)
        if self.cash <= 0:
            raise ValueError("starting_cash must be positive")
        self.max_open_exposure = (
            self.cash if max_open_exposure is None else D(max_open_exposure)
        )
        if self.max_open_exposure <= 0:
            raise ValueError("max_open_exposure must be positive")

        self.positions = {}
        # Latest externally supplied marks; deliberately refreshed after restart.
        self.mark_prices = {}
        self.seen_signal_ids = set()
        self.daily_realized = Decimal("0")
        self.daily_date = None

        self._restore()

    def _date(self, timestamp_ms):
        return datetime.fromtimestamp(
            timestamp_ms / 1000, tz=timezone.utc
        ).date().isoformat()

    def _roll_day(self, timestamp_ms):
        today = self._date(timestamp_ms)
        if self.daily_date != today:
            self.daily_date = today
            self.daily_realized = Decimal("0")

    def _round_qty(self, quantity):
        return (
            (quantity / self.qty_step).to_integral_value(rounding=ROUND_DOWN)
            * self.qty_step
        )

    def _state(self):
        return {
            "version": self.VERSION,
            "cash": str(self.cash),
            "positions": {
                symbol: {
                    "qty": str(position["qty"]),
                    "avg_cost": str(position["avg_cost"]),
                }
                for symbol, position in self.positions.items()
            },
            "seen_signal_ids": sorted(self.seen_signal_ids),
            "daily_realized": str(self.daily_realized),
            "daily_date": self.daily_date,
        }

    def _snapshot_mutable_state(self):
        return (
            self.cash,
            copy.deepcopy(self.positions),
            set(self.seen_signal_ids),
            self.daily_realized,
            self.daily_date,
        )

    def _restore_mutable_state(self, snapshot):
        (
            self.cash,
            self.positions,
            self.seen_signal_ids,
            self.daily_realized,
            self.daily_date,
        ) = snapshot

    def _persist_transaction(self, snapshot, journal_size):
        try:
            self._persist()
        except Exception:
            self._restore_mutable_state(snapshot)
            # Undo a partial append where possible so the journal remains readable.
            try:
                if os.path.exists(self.journal_path):
                    with open(self.journal_path, "r+b") as handle:
                        handle.truncate(journal_size)
                        handle.flush()
                        os.fsync(handle.fileno())
            except OSError:
                pass
            raise

    def _persist(self):
        directory = os.path.dirname(self.journal_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        record = {"type": "state", "state": self._state()}
        with open(self.journal_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _validated_state(self, state):
        if not isinstance(state, dict):
            raise ValueError("State must be an object")
        if state.get("version") != self.VERSION:
            raise ValueError("Unsupported journal version")

        cash = D(state["cash"])
        if cash < 0:
            raise ValueError("Journal cash cannot be negative")

        raw_positions = state["positions"]
        if not isinstance(raw_positions, dict):
            raise ValueError("Journal positions must be an object")
        positions = {}
        for symbol, raw in raw_positions.items():
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("Journal contains an invalid symbol")
            if not isinstance(raw, dict):
                raise ValueError("Journal position must be an object")
            qty = D(raw["qty"])
            avg_cost = D(raw["avg_cost"])
            if qty <= 0 or avg_cost <= 0:
                raise ValueError("Journal position values must be positive")
            if self._round_qty(qty) != qty:
                raise ValueError("Journal position quantity is off step")
            positions[symbol] = {"qty": qty, "avg_cost": avg_cost}

        raw_ids = state["seen_signal_ids"]
        if not isinstance(raw_ids, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw_ids
        ):
            raise ValueError("Journal signal IDs are invalid")
        if len(raw_ids) != len(set(raw_ids)):
            raise ValueError("Journal contains duplicate signal IDs")

        daily_realized = D(state["daily_realized"])
        daily_date = state["daily_date"]
        if daily_date is not None:
            if not isinstance(daily_date, str):
                raise ValueError("Journal daily date is invalid")
            if date.fromisoformat(daily_date).isoformat() != daily_date:
                raise ValueError("Journal daily date is invalid")

        return cash, positions, set(raw_ids), daily_realized, daily_date

    def _repair_incomplete_tail(self):
        """Discard only a final JSONL fragment lacking its terminating newline."""
        with open(self.journal_path, "r+b") as handle:
            content = handle.read()
            if content and not content.endswith(b"\n"):
                last_newline = content.rfind(b"\n")
                safe_size = last_newline + 1
                handle.truncate(safe_size)
                handle.flush()
                os.fsync(handle.fileno())

    def _restore(self):
        if not os.path.exists(self.journal_path):
            return

        try:
            self._repair_incomplete_tail()
        except OSError as exc:
            raise PaperTradeError("Journal recovery could not repair incomplete tail: " + str(exc)) from exc

        last_state = None
        with open(self.journal_path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict) or record.get("type") != "state":
                        raise ValueError("Unknown journal record")
                    state = record["state"]
                    validated = self._validated_state(state)
                    last_state = validated
                except Exception as exc:
                    raise PaperTradeError(
                        "Journal recovery failed at line "
                        + str(line_number) + ": " + str(exc)
                    ) from exc

        if last_state is not None:
            (
                self.cash,
                self.positions,
                self.seen_signal_ids,
                self.daily_realized,
                self.daily_date,
            ) = last_state

    def _unrealized_pnl(self):
        """Unrealized P&L for positions with a current supplied mark price."""
        return sum(
            (
                (self.mark_prices[symbol] - position["avg_cost"])
                * position["qty"]
                for symbol, position in self.positions.items()
                if symbol in self.mark_prices
            ),
            Decimal("0"),
        )

    @_synchronized
    def mark_to_market(self, prices):
        """Update marks from a caller-validated market snapshot.

        Marks are not persisted: callers must refresh them after process restart.
        """
        if not isinstance(prices, dict) or not prices:
            raise PaperTradeError("A non-empty symbol-to-price mapping is required")
        updated = {}
        for symbol, price in prices.items():
            if not isinstance(symbol, str) or not symbol.strip():
                raise PaperTradeError("Mark symbol is required")
            value = D(price)
            if value <= 0:
                raise PaperTradeError("Mark prices must be positive")
            updated[symbol] = value
        self.mark_prices.update(updated)
        return {
            "unrealized_pnl": self._unrealized_pnl(),
            "daily_realized": self.daily_realized,
            "risk_pnl": self.daily_realized + self._unrealized_pnl(),
        }

    def _open_exposure(self):
        """Conservative cost-basis notional of all currently open positions."""
        return sum(
            (position["qty"] * position["avg_cost"]
             for position in self.positions.values()),
            Decimal("0"),
        )

    def _check_signal(self, signal_id):
        if not isinstance(signal_id, str) or not signal_id.strip():
            raise PaperTradeError("signal_id is required")
        if signal_id in self.seen_signal_ids:
            raise PaperTradeError("Duplicate signal rejected")

    @_synchronized
    def buy(self, symbol, price, quantity, signal_id, timestamp_ms=None):
        if not isinstance(symbol, str) or not symbol.strip():
            raise PaperTradeError("Symbol is required")

        self._check_signal(signal_id)
        price = D(price)
        quantity = self._round_qty(D(quantity))

        if price <= 0 or quantity < self.min_qty:
            raise PaperTradeError("Invalid price or quantity")

        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        trade_date = self._date(timestamp_ms)
        effective_daily_realized = (
            self.daily_realized if self.daily_date == trade_date
            else Decimal("0")
        )

        risk_pnl = effective_daily_realized + self._unrealized_pnl()
        if risk_pnl <= -self.daily_loss_limit:
            raise PaperTradeError("Daily loss limit reached: entries blocked")

        fill_price = price * (1 + self.slippage_rate)
        notional = fill_price * quantity
        fee = notional * self.fee_rate
        total_cost = notional + fee

        if self._open_exposure() + total_cost > self.max_open_exposure:
            raise PaperTradeError("Maximum open exposure limit reached")
        if total_cost > self.cash:
            raise PaperTradeError("Insufficient paper cash")

        old = self.positions.get(symbol)
        old_qty = old["qty"] if old else Decimal("0")
        old_cost = old["avg_cost"] * old_qty if old else Decimal("0")
        new_qty = old_qty + quantity

        snapshot = self._snapshot_mutable_state()
        journal_size = os.path.getsize(self.journal_path) if os.path.exists(self.journal_path) else 0
        self._roll_day(timestamp_ms)
        self.cash -= total_cost
        self.positions[symbol] = {
            "qty": new_qty,
            "avg_cost": (old_cost + total_cost) / new_qty,
        }
        self.seen_signal_ids.add(signal_id)
        self._persist_transaction(snapshot, journal_size)

        return {
            "side": "BUY",
            "symbol": symbol,
            "quantity": quantity,
            "fill_price": fill_price,
            "fee": fee,
            "cash": self.cash,
        }

    @_synchronized
    def sell(self, symbol, price, quantity, signal_id, timestamp_ms=None):
        if not isinstance(symbol, str) or not symbol.strip():
            raise PaperTradeError("Symbol is required")

        self._check_signal(signal_id)
        price = D(price)
        quantity = self._round_qty(D(quantity))

        if price <= 0 or quantity < self.min_qty:
            raise PaperTradeError("Invalid price or quantity")

        position = self.positions.get(symbol)
        if position is None or quantity > position["qty"]:
            raise PaperTradeError("Insufficient paper position")

        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        fill_price = price * (1 - self.slippage_rate)
        notional = fill_price * quantity
        fee = notional * self.fee_rate
        proceeds = notional - fee

        cost_basis = position["avg_cost"] * quantity
        realized = proceeds - cost_basis

        snapshot = self._snapshot_mutable_state()
        journal_size = os.path.getsize(self.journal_path) if os.path.exists(self.journal_path) else 0
        self._roll_day(timestamp_ms)
        self.cash += proceeds
        remaining = position["qty"] - quantity

        if remaining == 0:
            del self.positions[symbol]
        else:
            position["qty"] = remaining

        self.daily_realized += realized
        self.seen_signal_ids.add(signal_id)
        self._persist_transaction(snapshot, journal_size)

        return {
            "side": "SELL",
            "symbol": symbol,
            "quantity": quantity,
            "fill_price": fill_price,
            "fee": fee,
            "realized_pnl": realized,
            "cash": self.cash,
        }

    @_synchronized
    def status(self):
        return {
            "cash": self.cash,
            "positions": copy.deepcopy(self.positions),
            "daily_realized": self.daily_realized,
            "unrealized_pnl": self._unrealized_pnl(),
            "risk_pnl": self.daily_realized + self._unrealized_pnl(),
            "daily_loss_limit": self.daily_loss_limit,
            "marked_symbols": sorted(self.mark_prices),
            "max_open_exposure": self.max_open_exposure,
            "open_exposure": self._open_exposure(),
            "daily_date": self.daily_date,
        }
