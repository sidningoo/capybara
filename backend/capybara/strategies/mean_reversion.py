"""Mean-reversion swing strategy.

Thesis: in range-bound / choppy markets, extreme short-term moves revert. Buy
oversold dips (z-score of price well below its 20-day mean, RSI low) — but only
while the longer-term trend is up (price above the 200-day SMA), so we're buying
dips in healthy names, not catching falling knives.

Best in: MEAN_REVERTING (and tolerable in QUIET).
"""
from __future__ import annotations

import pandas as pd

from capybara.models import Intent, Regime
from capybara.strategies.base import Strategy


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"
    suited_regimes = {Regime.MEAN_REVERTING, Regime.QUIET}
    max_weight = 0.15

    def __init__(self, z_entry: float = -1.5, z_exit: float = -0.2, rsi_oversold: float = 35.0):
        self.z_entry = z_entry
        self.z_exit = z_exit
        self.rsi_oversold = rsi_oversold

    def generate(self, symbol: str, feats: pd.DataFrame) -> Intent:
        if feats is None or feats.empty:
            return self._flat(symbol, "no data")
        row = feats.iloc[-1]
        required = ["close", "zscore_20", "rsi_14", "sma_200", "atr_14"]
        if any(pd.isna(row.get(c)) for c in required):
            return self._flat(symbol, "insufficient history")

        close = float(row["close"])
        z = float(row["zscore_20"])
        rsi = float(row["rsi_14"])
        long_uptrend = close > float(row["sma_200"])

        # Exit once price has reverted back toward the mean.
        if z >= self.z_exit:
            return self._flat(symbol, f"exit: reverted z={z:.2f}")

        # Only buy dips in longer-term uptrends.
        if not long_uptrend:
            return self._flat(symbol, "skip: below SMA200 (no falling knives)")

        # Entry: sufficiently oversold.
        if z <= self.z_entry and rsi <= self.rsi_oversold:
            depth = min(1.0, abs(z - self.z_entry) / 1.5 + 0.4)
            weight = self.max_weight * (0.5 + 0.5 * depth)
            confidence = min(1.0, 0.45 + depth / 2)
            atr = float(row["atr_14"])
            stop = close - 2.5 * atr
            return self._long(
                symbol,
                weight=weight,
                confidence=confidence,
                reason=f"mean-reversion: z={z:.2f}, rsi={rsi:.0f}, above SMA200",
                stop_loss=stop,
            )
        return self._flat(symbol, f"no entry: z={z:.2f}, rsi={rsi:.0f}")
