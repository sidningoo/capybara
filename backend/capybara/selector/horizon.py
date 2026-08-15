"""Auto horizon selection (Phase 3).

Lets the bot decide, per opportunity, whether a trade is a **swing** (days-to-weeks,
daily bars — the default) or an **intraday** play (hours), rather than being hard-wired
to one timeframe. This is the "it decides which trade is for which timeframe" capability.

The decision is a transparent function of volatility, short-vs-long momentum, and the
strength of any news catalyst. Intraday is only *proposed* here; actually executing it
requires the intraday data path (config `CAPYBARA_TIMEFRAME`), so when that path is off
the orchestrator keeps trading on the swing clock but still records the intent — the
plumbing is ready for Phase-3.5 to flip on.
"""
from __future__ import annotations

from dataclasses import dataclass

from capybara.models import Horizon


@dataclass
class HorizonPolicy:
    # Thresholds that flag a fast, catalyst-driven move worth trading intraday.
    atr_pct_fast: float = 0.03        # elevated intraday range (3%+ ATR)
    sentiment_catalyst: float = 0.5   # strong |news sentiment| = catalyst
    short_over_long_mom: float = 1.5  # 20d momentum this many× the 60d pace
    enabled: bool = True

    def decide(self, feats: dict[str, float], sentiment: float = 0.0) -> tuple[Horizon, str]:
        if not self.enabled or not feats:
            return Horizon.SWING, "swing (auto-horizon off)"

        atr_pct = feats.get("atr_pct", 0.0)
        mom_20 = feats.get("mom_20", 0.0)
        mom_60 = feats.get("mom_60", 0.0)

        catalyst = abs(sentiment) >= self.sentiment_catalyst
        high_vol = atr_pct >= self.atr_pct_fast
        # Short-term momentum accelerating vs the longer trend (per-day pace).
        pace_20 = abs(mom_20) / 20.0
        pace_60 = abs(mom_60) / 60.0 if mom_60 else 0.0
        accelerating = pace_60 > 0 and pace_20 >= self.short_over_long_mom * pace_60

        # Intraday needs a fast tape (vol) AND a reason it's moving now (catalyst or
        # sharply accelerating momentum).
        if high_vol and (catalyst or accelerating):
            why = []
            if catalyst:
                why.append(f"news catalyst {sentiment:+.2f}")
            if accelerating:
                why.append("momentum accelerating")
            why.append(f"ATR {atr_pct:.1%}")
            return Horizon.INTRADAY, "intraday: " + ", ".join(why)

        return Horizon.SWING, "swing (no fast catalyst)"
