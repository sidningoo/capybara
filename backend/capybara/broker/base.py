"""The BrokerAdapter interface.

This is the single most important boundary in Capybara. Everything above it
(strategies, selector, risk, orchestrator) is broker-agnostic. Two implementations
exist:

  * AlpacaBroker   — live paper trading against Alpaca
  * BacktestBroker — replays historical bars, simulates fills

Because both satisfy this interface, the *exact same* decision code is validated
in backtest before it is ever pointed at the paper account.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd

from capybara.models import Account, Order, Position


class BrokerAdapter(ABC):
    """Abstract broker + market-data access."""

    # ---- Market data ----
    @abstractmethod
    def get_bars(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Return {symbol: DataFrame[open, high, low, close, volume]} indexed by timestamp."""
        ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float | None:
        ...

    @abstractmethod
    def is_market_open(self) -> bool:
        ...

    # ---- Account / positions ----
    @abstractmethod
    def get_account(self) -> Account:
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        ...

    # ---- Orders ----
    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order; returns the order updated with broker id/status."""
        ...

    @abstractmethod
    def get_open_orders(self) -> list[Order]:
        ...

    @abstractmethod
    def get_order(self, broker_order_id: str) -> Order | None:
        ...

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> bool:
        ...

    @abstractmethod
    def cancel_all_orders(self) -> int:
        ...

    @abstractmethod
    def close_position(self, symbol: str) -> Order | None:
        ...

    @abstractmethod
    def close_all_positions(self) -> list[Order]:
        ...
