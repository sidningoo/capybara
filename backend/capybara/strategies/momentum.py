"""Momentum swing strategy (the Phase-1 anchor).

Thesis: trends persist over a horizon of days-to-weeks. Go long when price is in an
uptrend (above the 50-day SMA), medium-term momentum is positive, and MACD confirms —
but avoid chasing when RSI is already extremely overbought.

Best in: TRENDING_UP.
"""
from __future__ import annotations

import pandas as pd

from capybara.models import Intent, Regime
from capybara.strategies.base import Strategy


class MomentumStrategy(Strategy):
    name = "momentum"
    suited_regimes = {Regime.TRENDING_UP}
    max_weight = 0.20

    def __init__(self, mom_threshold: float = 0.02, rsi_overbought: float = 80.0, atr_stop_mult: float = 3.0):
        self.mom_threshold = mom_threshold
        self.rsi_overbought = rsi_overbought
        self.atr_stop_mult = atr_stop_mult

    def generate(self, symbol: str, feats: pd.DataFrame) -> Intent:
        if feats is None or feats.empty:
            return self._flat(symbol, "no data")
        row = feats.iloc[-1]
        required = ["close", "sma_50", "mom_20", "macd", "macd_signal", "rsi_14", "atr_14"]
        if any(pd.isna(row.get(c)) for c in required):
            return self._flat(symbol, "insufficient history")

        close = float(row["close"])
        uptrend = close > float(row["sma_50"])
        mom = float(row["mom_20"])
        macd_ok = float(row["macd"]) > float(row["macd_signal"])
        rsi = float(row["rsi_14"])

        # Exit condition: trend broken or momentum rolled over.
        if not uptrend or mom <= 0:
            return self._flat(symbol, f"exit: uptrend={uptrend}, mom={mom:.3f}")

        # Entry gate.
        if mom < self.mom_threshold or not macd_ok:
            return self._flat(symbol, f"no entry: mom={mom:.3f}, macd_ok={macd_ok}")
        if rsi >= self.rsi_overbought:
            return self._flat(symbol, f"skip: overbought rsi={rsi:.1f}")

        # Size by momentum strength (cap at max_weight); confidence scales with mom + MACD gap.
        strength = min(1.0, mom / (self.mom_threshold * 4))
        weight = self.max_weight * (0.5 + 0.5 * strength)
        confidence = min(1.0, 0.5 + strength / 2)
        atr = float(row["atr_14"])
        stop = close - self.atr_stop_mult * atr
        return self._long(
            symbol,
            weight=weight,
            confidence=confidence,
            reason=f"momentum: mom20={mom:.1%}, price>SMA50, MACD>signal, rsi={rsi:.0f}",
            stop_loss=stop,
        )
