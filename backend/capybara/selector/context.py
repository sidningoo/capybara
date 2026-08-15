"""Context vector construction for the learning selector.

The bandit reasons over a fixed, standardized feature vector (the "context").
`ContextScaler` learns per-feature mean/std during training and applies the same
transform at inference — persisted alongside the model so live and backtest match.

Keeping the feature list fixed and explicit (rather than "whatever columns exist")
makes the learned model stable and reproducible.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np

# Fixed context features (must all be produced by data/features.py).
CONTEXT_FEATURES: list[str] = [
    "adx_14",
    "vol_20",
    "mom_20",
    "mom_60",
    "rsi_14",
    "zscore_20",
    "atr_pct",
    "macd",
    "above_sma50",
    "above_sma200",
]


@dataclass
class ContextScaler:
    """Standardizes context features to ~N(0,1). A leading bias term (1.0) is
    prepended so linear models can fit an intercept."""
    mean: dict[str, float] = field(default_factory=dict)
    std: dict[str, float] = field(default_factory=dict)
    fitted: bool = False

    @property
    def dim(self) -> int:
        return len(CONTEXT_FEATURES) + 1  # +1 bias

    def partial_fit(self, rows: list[dict[str, float]]) -> None:
        """Fit mean/std from a batch of feature dicts (call once on training data)."""
        arr = np.array(
            [[row.get(f, 0.0) for f in CONTEXT_FEATURES] for row in rows], dtype=float
        )
        if arr.size == 0:
            return
        m = np.nanmean(arr, axis=0)
        s = np.nanstd(arr, axis=0)
        s[s == 0] = 1.0
        self.mean = {f: float(m[i]) for i, f in enumerate(CONTEXT_FEATURES)}
        self.std = {f: float(s[i]) for i, f in enumerate(CONTEXT_FEATURES)}
        self.fitted = True

    def transform(self, feats: dict[str, float]) -> np.ndarray:
        """Feature dict -> standardized vector with a leading bias term."""
        x = np.empty(self.dim, dtype=float)
        x[0] = 1.0  # bias
        for i, f in enumerate(CONTEXT_FEATURES):
            v = feats.get(f)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                x[i + 1] = 0.0
                continue
            mu = self.mean.get(f, 0.0)
            sd = self.std.get(f, 1.0)
            x[i + 1] = (float(v) - mu) / (sd if sd else 1.0)
        # Clip to keep the linear model numerically stable against outliers.
        return np.clip(x, -5.0, 5.0)

    def has(self, feats: dict[str, float]) -> bool:
        """True if the feature dict contains all context features (post-warmup)."""
        return all(f in feats for f in CONTEXT_FEATURES)

    # persistence
    def to_dict(self) -> dict:
        return {"mean": self.mean, "std": self.std, "fitted": self.fitted}

    @classmethod
    def from_dict(cls, d: dict) -> "ContextScaler":
        return cls(mean=d.get("mean", {}), std=d.get("std", {}), fitted=d.get("fitted", False))

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
