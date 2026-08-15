"""Backtest → selector feedback: learn the Stage-1 score table from history.

Closes the loop between backtesting and the rules-based `StrategySelector`. For each
bar it labels the regime and, for every strategy, records the realized forward return
whenever that strategy would have gone long. Averaging per (regime, strategy) and
squashing to 0..1 yields a data-driven replacement for the hand-set `DEFAULT_SCORES`.

Use it to answer "which strategy *actually* worked in which regime on this data?"
rather than trusting priors.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from capybara.data.features import compute_features
from capybara.logging_setup import get_logger
from capybara.models import Regime, SignalDirection
from capybara.regime.detector import RegimeDetector
from capybara.selector.context import CONTEXT_FEATURES
from capybara.strategies.registry import default_playbook

log = get_logger("backtest.attribution")


def compute_regime_scores(
    bars: dict[str, pd.DataFrame],
    horizon: int = 10,
    warmup: int = 205,
    score_scale: float = 0.6,
) -> dict[Regime, dict[str, float]]:
    """Return {regime: {strategy: score in 0..1}} learned from `bars`."""
    playbook = default_playbook()
    detector = RegimeDetector()

    # buckets[regime][strategy] -> list of realized forward returns (%) when long
    buckets: dict[Regime, dict[str, list[float]]] = {
        r: {name: [] for name in playbook} for r in Regime
    }

    for sym, raw in bars.items():
        df = compute_features(raw)
        if df is None or df.empty:
            continue
        closes = df["close"].to_numpy()
        n = len(df)
        for i in range(warmup, n - horizon):
            row = df.iloc[i]
            if not all(f in row and not pd.isna(row[f]) for f in CONTEXT_FEATURES):
                continue
            fvec = {f: float(row[f]) for f in CONTEXT_FEATURES}
            reading = detector.classify(sym, fvec)
            fwd_ret = (closes[i + horizon] / closes[i] - 1.0) * 100.0
            window = df.iloc[: i + 1]
            for name, strat in playbook.items():
                intent = strat.generate(sym, window)
                if intent.direction == SignalDirection.LONG and intent.target_weight > 0:
                    buckets[reading.regime][name].append(fwd_ret)

    # Aggregate: mean forward return -> logistic squash to 0..1.
    scores: dict[Regime, dict[str, float]] = {}
    for regime, per_strat in buckets.items():
        scores[regime] = {}
        for name, rets in per_strat.items():
            if not rets:
                scores[regime][name] = 0.0
                continue
            mean_ret = float(np.mean(rets))
            # logistic so a mean of 0% -> 0.5, positive -> up, negative -> down.
            scores[regime][name] = round(float(1.0 / (1.0 + np.exp(-mean_ret * score_scale))), 3)
    return scores


def save_scores(scores: dict[Regime, dict[str, float]], path: str) -> None:
    serial = {r.value: v for r, v in scores.items()}
    with open(path, "w") as fh:
        json.dump(serial, fh, indent=2)
    log.info("Saved regime scores to %s", path)


def load_scores(path: str) -> dict[Regime, dict[str, float]]:
    with open(path) as fh:
        serial = json.load(fh)
    return {Regime(k): v for k, v in serial.items()}
