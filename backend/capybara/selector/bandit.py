"""Contextual-bandit strategy selector (LinUCB, disjoint per-arm).

This is the Phase-2 upgrade to the static score table. It *learns* which strategy
tends to pay off given the current market context, and keeps a "cash" arm as a
baseline so it naturally stays out when nothing looks good.

Same public surface as `StrategySelector` (`select(reading) -> Selection`, plus
`pinned` / `blocked`), so the orchestrator can swap between them via config.

Model (disjoint LinUCB, Li et al. 2010):
    per arm a:  A_a = I (d×d),  b_a = 0 (d)
    theta_a = A_a^{-1} b_a
    ucb_a(x) = theta_a·x + alpha * sqrt(x·A_a^{-1}·x)
    pick argmax ucb_a ; after observing reward r: A_a += x xᵀ ; b_a += r x

`alpha` controls exploration. Trained offline (see backtest/walkforward.py) and
optionally updated online as realized rewards arrive.
"""
from __future__ import annotations

import io
import json

import numpy as np

from capybara.logging_setup import get_logger
from capybara.models import RegimeReading
from capybara.selector.context import ContextScaler
from capybara.selector.selector import Selection
from capybara.strategies.registry import CASH

log = get_logger("selector.bandit")


class LinUCBSelector:
    def __init__(
        self,
        arms: list[str] | None = None,
        alpha: float = 0.4,
        scaler: ContextScaler | None = None,
        min_confidence: float = 0.30,
    ):
        # Strategy arms + a cash baseline arm.
        self.arms: list[str] = arms or ["momentum", "mean_reversion", "breakout", CASH]
        self.alpha = alpha
        self.scaler = scaler or ContextScaler()
        self.min_confidence = min_confidence
        d = self.scaler.dim
        self.A: dict[str, np.ndarray] = {a: np.identity(d) for a in self.arms}
        self.b: dict[str, np.ndarray] = {a: np.zeros(d) for a in self.arms}
        # HILT overrides (mirror StrategySelector).
        self.pinned: str | None = None
        self.blocked: set[str] = set()
        self._current: dict[str, str] = {}

    # ───────────── inference ─────────────
    def _theta(self, arm: str) -> np.ndarray:
        return np.linalg.solve(self.A[arm], self.b[arm])

    def _ucb(self, arm: str, x: np.ndarray) -> tuple[float, float]:
        """Return (mean_estimate, ucb)."""
        A_inv = np.linalg.inv(self.A[arm])
        theta = A_inv @ self.b[arm]
        mean = float(theta @ x)
        bonus = self.alpha * float(np.sqrt(max(0.0, x @ A_inv @ x)))
        return mean, mean + bonus

    def select(self, reading: RegimeReading) -> Selection:
        sym = reading.symbol

        # HILT pin/blocks (same semantics as the rules selector).
        if self.pinned and self.pinned != CASH and self.pinned not in self.blocked:
            self._current[sym] = self.pinned
            return Selection(sym, self.pinned, 1.0, reading.regime, reading.confidence,
                             reason=f"pinned by operator ({self.pinned})")
        if self.pinned == CASH:
            self._current[sym] = CASH
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason="pinned to cash by operator")

        # Need the full context vector; otherwise cash.
        if not self.scaler.has(reading.features):
            self._current[sym] = CASH
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason="cash: insufficient features for bandit context")

        x = self.scaler.transform(reading.features)
        estimates: dict[str, float] = {}
        ucbs: dict[str, float] = {}
        for arm in self.arms:
            if arm in self.blocked:
                continue
            mean, ucb = self._ucb(arm, x)
            estimates[arm] = mean
            ucbs[arm] = ucb

        if not ucbs:
            self._current[sym] = CASH
            return Selection(sym, CASH, 0.0, reading.regime, reading.confidence,
                             reason="cash: all arms blocked")

        best = max(ucbs, key=lambda a: ucbs[a])
        best_est = estimates[best]
        cash_est = estimates.get(CASH, 0.0)

        # Confidence: how much the best arm beats the cash baseline (squashed 0..1).
        edge = best_est - cash_est
        confidence = float(1.0 / (1.0 + np.exp(-edge * 6.0)))  # logistic on the edge

        if best == CASH or confidence < self.min_confidence:
            self._current[sym] = CASH
            return Selection(sym, CASH, round(best_est, 4), reading.regime, confidence,
                             reason=f"cash: bandit edge {edge:+.3f} (conf {confidence:.2f})")

        self._current[sym] = best
        return Selection(sym, best, round(best_est, 4), reading.regime, confidence,
                         reason=f"bandit chose {best} (est {best_est:+.3f}, edge {edge:+.3f} vs cash)")

    # ───────────── learning ─────────────
    def update(self, arm: str, context: np.ndarray, reward: float) -> None:
        if arm not in self.A:
            return
        x = context.reshape(-1)
        self.A[arm] += np.outer(x, x)
        self.b[arm] += reward * x

    def update_from_features(self, arm: str, feats: dict[str, float], reward: float) -> None:
        self.update(arm, self.scaler.transform(feats), reward)

    # ───────────── persistence ─────────────
    def save(self, path: str) -> None:
        buffers = {}
        for a in self.arms:
            buffers[f"A__{a}"] = self.A[a]
            buffers[f"b__{a}"] = self.b[a]
        meta = {"arms": self.arms, "alpha": self.alpha,
                "min_confidence": self.min_confidence, "scaler": self.scaler.to_dict()}
        np.savez(path, meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8), **buffers)
        log.info("LinUCB model saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "LinUCBSelector":
        data = np.load(path, allow_pickle=False)
        meta = json.loads(bytes(data["meta"]).decode())
        scaler = ContextScaler.from_dict(meta["scaler"])
        sel = cls(arms=meta["arms"], alpha=meta["alpha"],
                  scaler=scaler, min_confidence=meta["min_confidence"])
        for a in sel.arms:
            sel.A[a] = data[f"A__{a}"]
            sel.b[a] = data[f"b__{a}"]
        log.info("LinUCB model loaded from %s", path)
        return sel

    def save_bytes(self) -> bytes:
        buf = io.BytesIO()
        buffers = {}
        for a in self.arms:
            buffers[f"A__{a}"] = self.A[a]
            buffers[f"b__{a}"] = self.b[a]
        meta = {"arms": self.arms, "alpha": self.alpha,
                "min_confidence": self.min_confidence, "scaler": self.scaler.to_dict()}
        np.savez(buf, meta=np.frombuffer(json.dumps(meta).encode(), dtype=np.uint8), **buffers)
        return buf.getvalue()
