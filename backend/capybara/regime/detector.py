"""Regime detection — Stage 1: interpretable, rules-based.

Maps a feature vector to one of the coarse `Regime` labels plus a confidence.
This is deliberately transparent so every decision can be explained in the UI
("chose momentum because ADX=31, price>SMA50, 20d momentum=+6%").

Phase 2+ replaces/augments this with a learned classifier (e.g., HMM or gradient
boosting) or feeds the raw feature vector straight into a contextual bandit — but
the `Regime` label survives as a human-readable projection either way.
"""
from __future__ import annotations

from capybara.logging_setup import get_logger
from capybara.models import Regime, RegimeReading

log = get_logger("regime.detector")


class RegimeDetector:
    def __init__(
        self,
        adx_trend: float = 25.0,
        adx_chop: float = 20.0,
        high_vol: float = 0.35,      # annualized realized vol threshold
        mom_flat: float = 0.01,      # |20d momentum| below this is "flat"
    ):
        self.adx_trend = adx_trend
        self.adx_chop = adx_chop
        self.high_vol = high_vol
        self.mom_flat = mom_flat

    def classify(self, symbol: str, feats: dict[str, float]) -> RegimeReading:
        # Not enough history to form indicators -> UNKNOWN (selector will go to cash).
        needed = ("adx_14", "vol_20", "mom_20", "above_sma50")
        if not feats or any(k not in feats for k in needed):
            return RegimeReading(symbol=symbol, regime=Regime.UNKNOWN, confidence=0.0, features=feats)

        adx = feats["adx_14"]
        vol = feats["vol_20"]
        mom = feats["mom_20"]
        above_50 = feats["above_sma50"] > 0.5

        # High volatility dominates — risk-off signal regardless of trend.
        if vol >= self.high_vol:
            conf = _clip((vol - self.high_vol) / self.high_vol + 0.5)
            return RegimeReading(symbol, Regime.HIGH_VOLATILITY, conf, feats)

        # Strong trend
        if adx >= self.adx_trend and abs(mom) >= self.mom_flat:
            conf = _clip((adx - self.adx_trend) / 25.0 + 0.5)
            if mom > 0 and above_50:
                return RegimeReading(symbol, Regime.TRENDING_UP, conf, feats)
            if mom < 0 and not above_50:
                return RegimeReading(symbol, Regime.TRENDING_DOWN, conf, feats)
            # Mixed signals (e.g., high ADX but momentum vs MA disagree) -> mean-reverting.
            return RegimeReading(symbol, Regime.MEAN_REVERTING, _clip(conf * 0.7), feats)

        # Choppy / low ADX
        if adx <= self.adx_chop:
            if abs(mom) < self.mom_flat and vol < self.high_vol * 0.5:
                # Very little movement -> quiet.
                conf = _clip((self.adx_chop - adx) / self.adx_chop + 0.4)
                return RegimeReading(symbol, Regime.QUIET, conf, feats)
            conf = _clip((self.adx_chop - adx) / self.adx_chop + 0.4)
            return RegimeReading(symbol, Regime.MEAN_REVERTING, conf, feats)

        # In-between ADX band -> weak/ambiguous.
        return RegimeReading(symbol, Regime.MEAN_REVERTING, 0.4, feats)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
