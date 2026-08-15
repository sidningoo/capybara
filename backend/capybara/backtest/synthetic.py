"""Synthetic OHLCV generator for offline testing.

Produces bars with deliberately *different regimes* stitched together (trending up,
choppy/mean-reverting, high-vol selloff, recovery) so the regime detector and
selector actually have distinct conditions to react to. Not for research — just
for smoke-testing the pipeline without a network/credentials.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_regime_series(
    n_days: int = 600,
    start_price: float = 100.0,
    seed: int = 7,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Segment the timeline into regimes: (drift_per_day, daily_vol)
    segments = [
        (0.0010, 0.010),   # gentle uptrend
        (0.0000, 0.020),   # choppy / mean-reverting
        (-0.0025, 0.035),  # high-vol selloff
        (0.0015, 0.012),   # recovery uptrend
        (0.0002, 0.008),   # quiet
    ]
    seg_len = n_days // len(segments)
    rets = []
    for drift, vol in segments:
        rets.append(rng.normal(drift, vol, seg_len))
    rets = np.concatenate(rets)
    n = len(rets)

    close = start_price * np.exp(np.cumsum(rets))
    # Build OHLC around close with intrabar noise.
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)

    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def make_universe(symbols: list[str], n_days: int = 600) -> dict[str, pd.DataFrame]:
    """Distinct synthetic series per symbol (different seeds)."""
    return {
        sym: make_regime_series(n_days=n_days, start_price=50 + 30 * i, seed=7 + i)
        for i, sym in enumerate(symbols)
    }
