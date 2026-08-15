"""In-memory broker that replays historical bars and simulates fills.

Implements the exact same BrokerAdapter interface as AlpacaBroker, so the whole
decision stack (features -> regime -> selector -> strategy -> risk -> execution)
runs unchanged in backtest.

Design choices / assumptions (documented so results are honest):
  * The backtester owns the clock and calls `set_now(ts)` as it steps bar-by-bar.
  * `get_bars` returns only data with timestamp <= now  -> NO LOOKAHEAD.
  * Market orders fill immediately at the current bar's close, adjusted by
    `slippage_bps`. `commission_per_share` is deducted from cash.
  * Long-only, cash account (no leverage/shorting) to match the Phase-1 scope.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from capybara.broker.base import BrokerAdapter
from capybara.logging_setup import get_logger
from capybara.models import (
    Account,
    Fill,
    Order,
    OrderStatus,
    Position,
    Side,
)

log = get_logger("broker.backtest")


class BacktestBroker(BrokerAdapter):
    def __init__(
        self,
        bars: dict[str, pd.DataFrame],
        starting_cash: float = 100_000.0,
        commission_per_share: float = 0.0,
        slippage_bps: float = 1.0,
    ):
        # Normalize columns to lowercase ohlcv, ensure sorted index.
        self._bars: dict[str, pd.DataFrame] = {}
        for sym, df in bars.items():
            d = df.copy()
            d.columns = [str(c).lower() for c in d.columns]
            d = d.sort_index()
            self._bars[sym] = d

        self._cash = starting_cash
        self._starting_cash = starting_cash
        self._commission = commission_per_share
        self._slippage = slippage_bps / 10_000.0
        # symbol -> (qty, avg_entry_price)
        self._positions: dict[str, list[float]] = {}
        self._orders: list[Order] = []
        self.fills: list[Fill] = []
        self._now: datetime | None = None

    # ─────────────── clock control (driven by the backtester) ───────────────
    def set_now(self, ts: datetime) -> None:
        self._now = ts

    @property
    def now(self) -> datetime | None:
        return self._now

    # ─────────────── Market data (no lookahead) ───────────────
    def get_bars(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        cutoff = self._now
        for sym in symbols:
            df = self._bars.get(sym)
            if df is None or df.empty:
                out[sym] = pd.DataFrame()
                continue
            sub = df if cutoff is None else df[df.index <= cutoff]
            if start is not None:
                sub = sub[sub.index >= start]
            if end is not None:
                sub = sub[sub.index <= end]
            if limit is not None:
                sub = sub.tail(limit)
            out[sym] = sub.copy()
        return out

    def get_latest_price(self, symbol: str) -> float | None:
        df = self._bars.get(symbol)
        if df is None or df.empty:
            return None
        sub = df if self._now is None else df[df.index <= self._now]
        if sub.empty:
            return None
        return float(sub["close"].iloc[-1])

    def is_market_open(self) -> bool:
        # In backtest we only ever step on bars, so the market is "open" per step.
        return True

    # ─────────────── Account / positions ───────────────
    def _equity(self) -> float:
        val = self._cash
        for sym, (qty, _) in self._positions.items():
            px = self.get_latest_price(sym) or 0.0
            val += qty * px
        return val

    def get_account(self) -> Account:
        eq = self._equity()
        return Account(equity=eq, cash=self._cash, buying_power=self._cash)

    def get_positions(self) -> list[Position]:
        out = []
        for sym, (qty, avg) in self._positions.items():
            if qty == 0:
                continue
            px = self.get_latest_price(sym) or avg
            out.append(Position(symbol=sym, qty=qty, avg_entry_price=avg, current_price=px))
        return out

    def get_position(self, symbol: str) -> Position | None:
        pos = self._positions.get(symbol)
        if not pos or pos[0] == 0:
            return None
        qty, avg = pos
        px = self.get_latest_price(symbol) or avg
        return Position(symbol=symbol, qty=qty, avg_entry_price=avg, current_price=px)

    # ─────────────── Orders ───────────────
    def submit_order(self, order: Order) -> Order:
        px = self.get_latest_price(order.symbol)
        if px is None:
            order.status = OrderStatus.REJECTED
            order.reason = (order.reason + " | no price").strip(" |")
            self._orders.append(order)
            return order

        # Apply slippage against us.
        fill_px = px * (1 + self._slippage) if order.side == Side.BUY else px * (1 - self._slippage)
        qty = order.qty
        cost = fill_px * qty
        commission = self._commission * qty

        if order.side == Side.BUY:
            total = cost + commission
            if total > self._cash + 1e-6:
                # Not enough cash — scale down to what we can afford (cash account).
                affordable = max(0.0, (self._cash - commission) / fill_px)
                qty = float(int(affordable))  # whole shares
                if qty <= 0:
                    order.status = OrderStatus.REJECTED
                    order.reason = (order.reason + " | insufficient cash").strip(" |")
                    self._orders.append(order)
                    return order
                cost = fill_px * qty
                commission = self._commission * qty
            self._cash -= cost + commission
            self._apply_position(order.symbol, qty, fill_px)
        else:  # SELL
            held = self._positions.get(order.symbol, [0.0, 0.0])[0]
            qty = min(qty, held)  # long-only: cannot sell more than held
            if qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = (order.reason + " | no shares to sell").strip(" |")
                self._orders.append(order)
                return order
            self._cash += fill_px * qty - commission
            self._apply_position(order.symbol, -qty, fill_px)

        order.qty = qty
        order.filled_qty = qty
        order.filled_avg_price = fill_px
        order.status = OrderStatus.FILLED
        order.broker_order_id = f"bt-{len(self._orders)}"
        order.updated_at = self._now or datetime.now(timezone.utc)
        self._orders.append(order)
        self.fills.append(
            Fill(
                symbol=order.symbol,
                side=order.side,
                qty=qty,
                price=fill_px,
                order_id=order.broker_order_id,
                timestamp=order.updated_at,
            )
        )
        return order

    def _apply_position(self, symbol: str, delta_qty: float, price: float) -> None:
        qty, avg = self._positions.get(symbol, [0.0, 0.0])
        new_qty = qty + delta_qty
        if delta_qty > 0:  # buying: recompute weighted avg
            avg = (qty * avg + delta_qty * price) / new_qty if new_qty else 0.0
        if abs(new_qty) < 1e-9:
            new_qty = 0.0
            avg = 0.0
        self._positions[symbol] = [new_qty, avg]

    def get_open_orders(self) -> list[Order]:
        # Backtest fills are immediate, so nothing stays open.
        return []

    def get_order(self, broker_order_id: str) -> Order | None:
        for o in self._orders:
            if o.broker_order_id == broker_order_id:
                return o
        return None

    def cancel_order(self, broker_order_id: str) -> bool:
        return False  # nothing to cancel; fills are immediate

    def cancel_all_orders(self) -> int:
        return 0

    def close_position(self, symbol: str) -> Order | None:
        pos = self.get_position(symbol)
        if not pos:
            return None
        return self.submit_order(Order(symbol=symbol, side=Side.SELL, qty=pos.qty, reason="close"))

    def close_all_positions(self) -> list[Order]:
        out = []
        for pos in self.get_positions():
            o = self.close_position(pos.symbol)
            if o:
                out.append(o)
        return out
