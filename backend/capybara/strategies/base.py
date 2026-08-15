"""Strategy base class.

A Strategy is a pure function of (symbol, feature frame) -> Intent. It NEVER:
  * talks to the broker,
  * knows about account size, cash, or other positions,
  * sizes itself against portfolio limits.

It only expresses *conviction* via `target_weight` (a desired fraction of equity
for this one symbol) and direction. The RiskManager owns all portfolio-level
decisions (caps, gross exposure, concurrent positions, guardrails). This clean
split is what lets the selector swap strategies freely and lets a human override
without fighting the strategy's internal state.

Each strategy also declares `suited_regimes` — the market conditions it is designed
for. The selector uses this together with backtested performance to choose.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from capybara.models import Intent, Regime, SignalDirection


class Strategy(ABC):
    #: Unique, stable name (used as a key in performance tables + the UI).
    name: str = "base"
    #: Regimes this strategy is designed to exploit.
    suited_regimes: set[Regime] = set()
    #: Max fraction of equity this strategy will ever request for one symbol.
    max_weight: float = 0.20

    @abstractmethod
    def generate(self, symbol: str, feats: pd.DataFrame) -> Intent:
        """Produce an Intent for `symbol` given its feature frame (indicators appended).

        Return a FLAT intent (target_weight=0) to express "no position / exit".
        """
        ...

    # Convenience constructors so subclasses stay terse.
    def _flat(self, symbol: str, reason: str) -> Intent:
        return Intent(
            symbol=symbol,
            direction=SignalDirection.FLAT,
            target_weight=0.0,
            strategy=self.name,
            confidence=0.0,
            reason=reason,
        )

    def _long(
        self,
        symbol: str,
        weight: float,
        confidence: float,
        reason: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Intent:
        return Intent(
            symbol=symbol,
            direction=SignalDirection.LONG,
            target_weight=max(0.0, min(self.max_weight, weight)),
            strategy=self.name,
            confidence=max(0.0, min(1.0, confidence)),
            reason=reason,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
