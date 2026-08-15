"""Strategy selector — Stage 1.

Decides, per symbol, WHICH strategy should be active given the detected regime.
It reasons over a performance table `scores[regime][strategy] -> expected score`
(0..1), which is seeded with sensible priors and can be overwritten from backtest
results (`load_scores`). Stage 2 will replace the static table with an online
contextual bandit, but the public interface (`select`) stays the same.

Three safety behaviours built in:
  1. Confidence floor: if the regime is UNKNOWN or its confidence is below
     `min_confidence`, we return CASH. "Not trading" is a valid decision.
  2. Score floor: if the best strategy's expected score is below `min_score`
     (e.g., every strategy is bad in TRENDING_DOWN for a long-only book), CASH.
  3. Hysteresis: we don't switch away from the current strategy unless a
     challenger beats it by `switch_margin`. Prevents whipsaw flip-flopping.

HILT overrides:
  * `pinned`: force a specific strategy for all symbols (human override).
  * `blocked`: never select these strategies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from capybara.logging_setup import get_logger
from capybara.models import Horizon, Regime, RegimeReading, utcnow
from capybara.strategies.registry import CASH

log = get_logger("selector")


# Prior expected scores per (regime, strategy). Long-only book, so downtrends
# favour cash. These are starting points; backtests refine them.
DEFAULT_SCORES: dict[Regime, dict[str, float]] = {
    Regime.TRENDING_UP:     {"momentum": 0.80, "breakout": 0.70, "mean_reversion": 0.20},
    Regime.TRENDING_DOWN:   {"momentum": 0.10, "breakout": 0.10, "mean_reversion": 0.10},
    Regime.MEAN_REVERTING:  {"momentum": 0.25, "breakout": 0.30, "mean_reversion": 0.70},
    Regime.HIGH_VOLATILITY: {"momentum": 0.25, "breakout": 0.40, "mean_reversion": 0.20},
    Regime.QUIET:           {"momentum": 0.25, "breakout": 0.20, "mean_reversion": 0.50},
    Regime.UNKNOWN:         {"momentum": 0.00, "breakout": 0.00, "mean_reversion": 0.00},
}


@dataclass(frozen=True, slots=True)
class Selection:
    symbol: str
    strategy: str            # a strategy name, or CASH
    score: float
    regime: Regime
    confidence: float
    reason: str
    sentiment: float = 0.0                 # news sentiment [-1..1] at decision time
    horizon: Horizon = Horizon.SWING       # chosen holding horizon
    timestamp: datetime = field(default_factory=utcnow)

    @property
    def is_cash(self) -> bool:
        return self.strategy == CASH


class StrategySelector:
    def __init__(
        self,
        scores: dict[Regime, dict[str, float]] | None = None,
        min_confidence: float = 0.35,
        min_score: float = 0.35,
        switch_margin: float = 0.10,
    ):
        self.scores = scores or {r: dict(v) for r, v in DEFAULT_SCORES.items()}
        self.min_confidence = min_confidence
        self.min_score = min_score
        self.switch_margin = switch_margin
        # HILT overrides (set by orchestrator/API):
        self.pinned: str | None = None
        self.blocked: set[str] = set()
        # per-symbol current selection (for hysteresis):
        self._current: dict[str, str] = {}

    def load_scores(self, scores: dict[Regime, dict[str, float]]) -> None:
        """Replace the performance table (e.g., from backtest attribution)."""
        self.scores = {r: dict(v) for r, v in scores.items()}
        log.info("Selector scores updated from external source.")

    def select(self, reading: RegimeReading) -> Selection:
        sym = reading.symbol

        # HILT: hard pin overrides everything (except a blocked pin).
        if self.pinned and self.pinned != CASH and self.pinned not in self.blocked:
            self._current[sym] = self.pinned
            return Selection(sym, self.pinned, 1.0, reading.regime, reading.confidence,
                             reason=f"pinned by operator ({self.pinned})")
        if self.pinned == CASH:
            self._current[sym] = CASH
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason="pinned to cash by operator")

        # Safety 1: low-confidence / unknown regime -> cash.
        if reading.regime == Regime.UNKNOWN or reading.confidence < self.min_confidence:
            self._current[sym] = CASH
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason=f"cash: regime {reading.regime.value} conf={reading.confidence:.2f} < {self.min_confidence}")

        table = self.scores.get(reading.regime, {})
        # Filter out blocked strategies.
        candidates = {k: v for k, v in table.items() if k not in self.blocked}
        if not candidates:
            self._current[sym] = CASH
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason="cash: no eligible strategies")

        best = max(candidates, key=lambda k: candidates[k])
        best_score = candidates[best]

        # Safety 2: even the best strategy is poor here -> cash.
        if best_score < self.min_score:
            self._current[sym] = CASH
            return Selection(sym, CASH, best_score, reading.regime, reading.confidence,
                             reason=f"cash: best {best}={best_score:.2f} < min_score {self.min_score}")

        # Safety 3: hysteresis — stick with current unless challenger clears margin.
        current = self._current.get(sym)
        if current and current in candidates and current != best:
            if best_score - candidates[current] < self.switch_margin:
                return Selection(sym, current, candidates[current], reading.regime, reading.confidence,
                                 reason=f"kept {current} (hysteresis; {best}+{best_score - candidates[current]:.2f} < {self.switch_margin})")

        self._current[sym] = best
        return Selection(sym, best, best_score, reading.regime, reading.confidence,
                         reason=f"selected {best} for {reading.regime.value} (score={best_score:.2f})")
