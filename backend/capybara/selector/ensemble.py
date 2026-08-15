"""Ensemble selector — always routes to the blended `ensemble` strategy.

Mirrors the `StrategySelector` public surface (`select`, `pinned`, `blocked`) so it's
a drop-in via `CAPYBARA_SELECTOR=ensemble`. It still respects the regime confidence
floor (unknown/low-confidence regimes → cash), then hands off to the EnsembleStrategy
which does the actual multi-strategy blending.
"""
from __future__ import annotations

from capybara.models import Regime, RegimeReading
from capybara.selector.selector import Selection
from capybara.strategies.registry import CASH

ENSEMBLE = "ensemble"


class EnsembleSelector:
    def __init__(self, min_confidence: float = 0.35):
        self.min_confidence = min_confidence
        self.pinned: str | None = None
        self.blocked: set[str] = set()

    def select(self, reading: RegimeReading) -> Selection:
        sym = reading.symbol
        if self.pinned == CASH:
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason="pinned to cash by operator")
        if reading.regime == Regime.UNKNOWN or reading.confidence < self.min_confidence:
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason=f"cash: regime {reading.regime.value} conf={reading.confidence:.2f}")
        return Selection(sym, ENSEMBLE, reading.confidence, reading.regime, reading.confidence,
                         reason=f"ensemble blend for {reading.regime.value}")
