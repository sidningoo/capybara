"""Alpaca implementation of BrokerAdapter (paper trading).

alpaca-py is imported lazily inside __init__ so the rest of Capybara (backtests,
unit tests, the selector) can run in environments where the SDK / network is not
available. Only when you actually construct an AlpacaBroker do you need it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd

from capybara.broker.base import BrokerAdapter
from capybara.logging_setup import get_logger
from capybara.models import (
    Account,
    Order,
    OrderClass,
    OrderStatus,
    OrderType,
    Position,
    Side,
    TimeInForce,
)

log = get_logger("broker.alpaca")


# Map Capybara timeframe strings -> alpaca TimeFrame objects (built lazily).
def _to_alpaca_timeframe(timeframe: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf = timeframe.lower().strip()
    table = {
        "1min": TimeFrame(1, TimeFrameUnit.Minute),
        "5min": TimeFrame(5, TimeFrameUnit.Minute),
        "15min": TimeFrame(15, TimeFrameUnit.Minute),
        "1hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1day": TimeFrame.Day,
    }
    return table.get(tf, TimeFrame.Day)


# Map Alpaca order status strings -> our OrderStatus enum.
_STATUS_MAP = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.SUBMITTED,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "done_for_day": OrderStatus.SUBMITTED,
    "canceled": OrderStatus.CANCELED,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.SUBMITTED,
    "pending_cancel": OrderStatus.SUBMITTED,
    "pending_replace": OrderStatus.SUBMITTED,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.SUBMITTED,
    "stopped": OrderStatus.SUBMITTED,
}


class AlpacaBroker(BrokerAdapter):
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        if not api_key or not secret_key:
            raise ValueError("Alpaca API key/secret are required for AlpacaBroker.")
        # Lazy imports — keep SDK optional for backtests.
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient

        self._paper = paper
        self._trading = TradingClient(api_key, secret_key, paper=paper)
        self._data = StockHistoricalDataClient(api_key, secret_key)
        log.info("AlpacaBroker initialized (paper=%s)", paper)

    # ─────────────── Market data ───────────────
    def get_bars(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        from alpaca.data.requests import StockBarsRequest

        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=_to_alpaca_timeframe(timeframe),
            start=start,
            end=end,
            limit=limit,
        )
        resp = self._data.get_stock_bars(req)
        out: dict[str, pd.DataFrame] = {}
        try:
            df = resp.df  # MultiIndex (symbol, timestamp)
        except Exception:  # pragma: no cover
            return {s: pd.DataFrame() for s in symbols}
        if df is None or df.empty:
            return {s: pd.DataFrame() for s in symbols}
        for sym in symbols:
            if sym in df.index.get_level_values(0):
                sub = df.xs(sym, level=0).copy()
                sub = sub.rename(columns=str.lower)
                cols = [c for c in ["open", "high", "low", "close", "volume"] if c in sub.columns]
                out[sym] = sub[cols]
            else:
                out[sym] = pd.DataFrame()
        return out

    def get_latest_price(self, symbol: str) -> float | None:
        from alpaca.data.requests import StockLatestTradeRequest

        try:
            req = StockLatestTradeRequest(symbol_or_symbols=symbol)
            resp = self._data.get_stock_latest_trade(req)
            trade = resp.get(symbol)
            return float(trade.price) if trade else None
        except Exception as exc:  # pragma: no cover
            log.warning("latest price failed for %s: %s", symbol, exc)
            return None

    def is_market_open(self) -> bool:
        try:
            return bool(self._trading.get_clock().is_open)
        except Exception as exc:  # pragma: no cover
            log.warning("clock check failed: %s", exc)
            return False

    # ─────────────── Account / positions ───────────────
    def get_account(self) -> Account:
        a = self._trading.get_account()
        return Account(
            equity=float(a.equity),
            cash=float(a.cash),
            buying_power=float(a.buying_power),
            currency=getattr(a, "currency", "USD"),
        )

    def get_positions(self) -> list[Position]:
        out = []
        for p in self._trading.get_all_positions():
            out.append(
                Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price or p.avg_entry_price),
                )
            )
        return out

    def get_position(self, symbol: str) -> Position | None:
        try:
            p = self._trading.get_open_position(symbol)
        except Exception:
            return None
        return Position(
            symbol=p.symbol,
            qty=float(p.qty),
            avg_entry_price=float(p.avg_entry_price),
            current_price=float(p.current_price or p.avg_entry_price),
        )

    # ─────────────── Orders ───────────────
    def submit_order(self, order: Order) -> Order:
        from alpaca.trading.enums import OrderClass as AOrderClass
        from alpaca.trading.enums import OrderSide
        from alpaca.trading.enums import TimeInForce as ATif
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        side = OrderSide.BUY if order.side == Side.BUY else OrderSide.SELL
        tif = ATif.GTC if order.time_in_force == TimeInForce.GTC else ATif.DAY
        client_id = order.client_order_id or f"cap-{uuid.uuid4().hex[:16]}"

        # Bracket entry: attach protective stop-loss + take-profit (BUY entries only).
        is_bracket = (
            order.order_class == OrderClass.BRACKET
            and order.side == Side.BUY
            and order.stop_loss_price is not None
        )
        if is_bracket:
            kwargs = dict(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=ATif.GTC,
                order_class=AOrderClass.BRACKET, client_order_id=client_id,
                stop_loss=StopLossRequest(stop_price=round(order.stop_loss_price, 2)),
            )
            if order.take_profit_price is not None:
                kwargs["take_profit"] = TakeProfitRequest(limit_price=round(order.take_profit_price, 2))
            req = MarketOrderRequest(**kwargs)
        elif order.order_type == OrderType.LIMIT and order.limit_price is not None:
            req = LimitOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
                limit_price=order.limit_price, client_order_id=client_id,
            )
        else:
            req = MarketOrderRequest(
                symbol=order.symbol, qty=order.qty, side=side, time_in_force=tif,
                client_order_id=client_id,
            )
        placed = self._trading.submit_order(order_data=req)
        return self._merge_broker_order(order, placed, client_id)

    def get_open_orders(self) -> list[Order]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        raw = self._trading.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN))
        return [self._from_broker_order(o) for o in raw]

    def get_order(self, broker_order_id: str) -> Order | None:
        try:
            o = self._trading.get_order_by_id(broker_order_id)
        except Exception:
            return None
        return self._from_broker_order(o)

    def cancel_order(self, broker_order_id: str) -> bool:
        try:
            self._trading.cancel_order_by_id(broker_order_id)
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("cancel failed for %s: %s", broker_order_id, exc)
            return False

    def cancel_all_orders(self) -> int:
        try:
            resp = self._trading.cancel_orders()
            return len(resp) if resp else 0
        except Exception as exc:  # pragma: no cover
            log.warning("cancel_all failed: %s", exc)
            return 0

    def close_position(self, symbol: str) -> Order | None:
        try:
            o = self._trading.close_position(symbol)
            return self._from_broker_order(o)
        except Exception as exc:  # pragma: no cover
            log.warning("close_position failed for %s: %s", symbol, exc)
            return None

    def close_all_positions(self) -> list[Order]:
        try:
            resp = self._trading.close_all_positions(cancel_orders=True)
            out = []
            for item in resp or []:
                body = getattr(item, "body", None)
                if body is not None:
                    out.append(self._from_broker_order(body))
            return out
        except Exception as exc:  # pragma: no cover
            log.warning("close_all_positions failed: %s", exc)
            return []

    # ─────────────── mapping helpers ───────────────
    def _merge_broker_order(self, order: Order, placed, client_id: str) -> Order:
        order.broker_order_id = str(placed.id)
        order.client_order_id = client_id
        order.status = _STATUS_MAP.get(str(placed.status.value).lower(), OrderStatus.SUBMITTED)
        if placed.filled_qty:
            order.filled_qty = float(placed.filled_qty)
        if placed.filled_avg_price:
            order.filled_avg_price = float(placed.filled_avg_price)
        order.updated_at = datetime.now(timezone.utc)
        return order

    def _from_broker_order(self, o) -> Order:
        return Order(
            symbol=o.symbol,
            side=Side.BUY if str(o.side.value).lower() == "buy" else Side.SELL,
            qty=float(o.qty or 0),
            order_type=OrderType.LIMIT if "limit" in str(o.order_type.value).lower() else OrderType.MARKET,
            time_in_force=TimeInForce.GTC if str(o.time_in_force.value).lower() == "gtc" else TimeInForce.DAY,
            limit_price=float(o.limit_price) if getattr(o, "limit_price", None) else None,
            status=_STATUS_MAP.get(str(o.status.value).lower(), OrderStatus.SUBMITTED),
            filled_qty=float(o.filled_qty or 0),
            filled_avg_price=float(o.filled_avg_price) if getattr(o, "filled_avg_price", None) else None,
            client_order_id=getattr(o, "client_order_id", "") or "",
            broker_order_id=str(o.id),
        )
