"""Ensemble strategy — blends the whole playbook into one position.

Instead of the selector choosing a single strategy, the ensemble runs every
sub-strategy and combines their intents into one confidence-weighted target. When
multiple independent strategies agree on a name, conviction (and size) rises; when
they disagree, exposure shrinks. A diversified alternative to winner-take-all.
"""
from __future__ import annotations

import pandas as pd

from capybara.models import Intent, Regime, SignalDirection
from capybara.strategies.base import Strategy


class EnsembleStrategy(Strategy):
    name = "ensemble"
    suited_regimes = set(Regime)
    max_weight = 0.20

    def __init__(self, sub_strategies: list[Strategy]):
        self.subs = sub_strategies

    def generate(self, symbol: str, feats: pd.DataFrame) -> Intent:
        longs: list[Intent] = []
        for s in self.subs:
            intent = s.generate(symbol, feats)
            if intent.direction == SignalDirection.LONG and intent.target_weight > 0:
                longs.append(intent)

        if not longs:
            return self._flat(symbol, "ensemble: no sub-strategy is long")

        # Confidence-weighted blend of target weights, capped at max_weight.
        total_conf = sum(i.confidence for i in longs) or 1.0
        blended = sum(i.target_weight * i.confidence for i in longs) / total_conf
        # Agreement bonus: scale by the fraction of strategies that agree.
        agreement = len(longs) / max(len(self.subs), 1)
        weight = min(self.max_weight, blended * (0.6 + 0.4 * agreement))
        confidence = min(1.0, (sum(i.confidence for i in longs) / len(longs)) * (0.7 + 0.3 * agreement))

        # Use the tightest (highest) stop among contributors for safety.
        stops = [i.stop_loss for i in longs if i.stop_loss is not None]
        stop = max(stops) if stops else None
        names = "+".join(sorted({i.strategy for i in longs}))
        return self._long(
            symbol,
            weight=weight,
            confidence=confidence,
            reason=f"ensemble: {len(longs)}/{len(self.subs)} agree ({names})",
            stop_loss=stop,
        )
