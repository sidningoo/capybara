"""Breakout / trend-following swing strategy (Donchian-style).

Thesis: when price closes above its recent range high on expanding volatility, a
new leg often follows. Enter on a 20-day high breakout confirmed by price above
the 50-day SMA; exit when price falls back below the 20-day SMA.

Best in: TRENDING_UP and the start of HIGH_VOLATILITY expansions (breakouts often
coincide with volatility pickups), so it complements pure momentum.
"""
from __future__ import annotations

import pandas as pd

from capybara.models import Intent, Regime
from capybara.strategies.base import Strategy


class BreakoutStrategy(Strategy):
    name = "breakout"
    suited_regimes = {Regime.TRENDING_UP, Regime.HIGH_VOLATILITY}
    max_weight = 0.18

    def __init__(self, breakout_buffer: float = 0.0, atr_stop_mult: float = 2.5):
        self.breakout_buffer = breakout_buffer  # e.g., require close >= hh_20 * (1+buffer)
        self.atr_stop_mult = atr_stop_mult

    def generate(self, symbol: str, feats: pd.DataFrame) -> Intent:
        if feats is None or feats.empty:
            return self._flat(symbol, "no data")
        if len(feats) < 2:
            return self._flat(symbol, "insufficient history")
        row = feats.iloc[-1]
        prev = feats.iloc[-2]
        required = ["close", "hh_20", "sma_20", "sma_50", "atr_14"]
        if any(pd.isna(row.get(c)) for c in required):
            return self._flat(symbol, "insufficient history")

        close = float(row["close"])
        sma_20 = float(row["sma_20"])
        sma_50 = float(row["sma_50"])
        # Use the PRIOR bar's 20-day high as the breakout level (rolling max of the
        # current bar already includes today, which would make the test trivial).
        prior_hh = float(prev["hh_20"])

        # Exit: close back below the 20-day SMA -> trend leg over.
        if close < sma_20:
            return self._flat(symbol, f"exit: close<{sma_20:.2f} (SMA20)")

        broke_out = close >= prior_hh * (1 + self.breakout_buffer)
        trend_ok = close > sma_50

        if broke_out and trend_ok:
            atr = float(row["atr_14"])
            # Confidence scales with how decisively it cleared the level.
            margin = (close - prior_hh) / prior_hh if prior_hh else 0.0
            confidence = min(1.0, 0.55 + margin * 20)
            weight = self.max_weight * (0.6 + 0.4 * min(1.0, margin * 40))
            stop = close - self.atr_stop_mult * atr
            return self._long(
                symbol,
                weight=weight,
                confidence=confidence,
                reason=f"breakout: close {close:.2f} >= 20d high {prior_hh:.2f}, above SMA50",
                stop_loss=stop,
            )
        return self._flat(symbol, f"no breakout: close={close:.2f}, 20d high={prior_hh:.2f}")
