"""Offline bandit training + walk-forward validation.

`BanditTrainer` teaches the LinUCB selector, off-policy, from history: at each bar
it asks every strategy what it *would* have done and rewards the corresponding arm
by the realized forward return over a holding horizon. The "cash" arm always earns
zero, so it becomes the do-nothing baseline.

`WalkForwardValidator` guards against overfitting the classic way: it rolls a
train→test window forward through time, training the selector only on past data and
measuring performance strictly out-of-sample. Reporting in-sample numbers on a
strategy selector is how people fool themselves; this makes that mistake hard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from capybara.config import Settings, get_settings
from capybara.data.features import compute_features
from capybara.logging_setup import get_logger
from capybara.models import Regime, SignalDirection
from capybara.regime.detector import RegimeDetector
from capybara.selector.bandit import LinUCBSelector
from capybara.selector.context import CONTEXT_FEATURES, ContextScaler
from capybara.strategies.registry import CASH, default_playbook

log = get_logger("backtest.walkforward")


class BanditTrainer:
    def __init__(self, horizon: int = 10, alpha: float = 0.4, warmup: int = 205):
        self.horizon = horizon
        self.alpha = alpha
        self.warmup = warmup
        self.playbook = default_playbook()
        self.detector = RegimeDetector()

    def _featurize(self, bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        return {s: compute_features(df) for s, df in bars.items()}

    def train(
        self,
        bars: dict[str, pd.DataFrame],
        up_to: datetime | None = None,
    ) -> LinUCBSelector:
        feats = self._featurize(bars)

        # ── Pass 1: fit the scaler on all post-warmup context rows (<= up_to). ──
        rows: list[dict[str, float]] = []
        for df in feats.values():
            if df is None or df.empty:
                continue
            sub = df if up_to is None else df[df.index <= up_to]
            for i in range(self.warmup, len(sub)):
                row = sub.iloc[i]
                if all(f in row and not pd.isna(row[f]) for f in CONTEXT_FEATURES):
                    rows.append({f: float(row[f]) for f in CONTEXT_FEATURES})
        scaler = ContextScaler()
        scaler.partial_fit(rows)

        sel = LinUCBSelector(alpha=self.alpha, scaler=scaler)

        # ── Pass 2: off-policy updates from realized forward returns. ──
        updates = 0
        for sym, df in feats.items():
            if df is None or df.empty:
                continue
            sub = df if up_to is None else df[df.index <= up_to]
            closes = sub["close"].to_numpy()
            n = len(sub)
            for i in range(self.warmup, n - self.horizon):
                row = sub.iloc[i]
                if not all(f in row and not pd.isna(row[f]) for f in CONTEXT_FEATURES):
                    continue
                fvec = {f: float(row[f]) for f in CONTEXT_FEATURES}
                x = scaler.transform(fvec)
                fwd_ret = (closes[i + self.horizon] / closes[i] - 1.0) * 100.0  # percent

                window = sub.iloc[: i + 1]
                for arm in sel.arms:
                    if arm == CASH:
                        sel.update(CASH, x, 0.0)  # baseline
                        continue
                    strat = self.playbook.get(arm)
                    if strat is None:
                        continue
                    intent = strat.generate(sym, window)
                    if intent.direction == SignalDirection.LONG and intent.target_weight > 0:
                        conviction = intent.target_weight / max(strat.max_weight, 1e-9)
                        reward = conviction * fwd_ret
                    else:
                        reward = 0.0  # strategy stayed out -> same as cash
                    sel.update(arm, x, reward)
                    updates += 1
        log.info("Bandit trained: %d scaler rows, %d arm updates (horizon=%d).",
                 len(rows), updates, self.horizon)
        return sel


@dataclass
class FoldResult:
    train_end: str
    test_start: str
    test_end: str
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    num_trades: int


@dataclass
class WalkForwardReport:
    folds: list[FoldResult] = field(default_factory=list)

    @property
    def oos_mean_return(self) -> float:
        return float(np.mean([f.total_return_pct for f in self.folds])) if self.folds else 0.0

    @property
    def oos_mean_sharpe(self) -> float:
        return float(np.mean([f.sharpe for f in self.folds])) if self.folds else 0.0

    def summary(self) -> str:
        lines = [f"Walk-forward: {len(self.folds)} folds | "
                 f"OOS mean return {self.oos_mean_return:+.2f}% | "
                 f"OOS mean Sharpe {self.oos_mean_sharpe:.2f}"]
        for i, f in enumerate(self.folds):
            lines.append(f"  fold {i+1}: test {f.test_start[:10]}→{f.test_end[:10]} "
                         f"ret={f.total_return_pct:+.2f}% maxDD={f.max_drawdown_pct:.2f}% "
                         f"Sharpe={f.sharpe:.2f} trades={f.num_trades}")
        return "\n".join(lines)


class WalkForwardValidator:
    def __init__(
        self,
        bars: dict[str, pd.DataFrame],
        settings: Settings | None = None,
        n_folds: int = 4,
        horizon: int = 10,
        warmup: int = 210,
    ):
        self.bars = bars
        self.s = settings or get_settings()
        self.n_folds = n_folds
        self.horizon = horizon
        self.warmup = warmup

    def run(self) -> WalkForwardReport:
        from capybara.backtest.runner import Backtester

        timeline = sorted({ts for df in self.bars.values() for ts in df.index})
        if len(timeline) < self.warmup + self.n_folds * 40:
            raise ValueError("Not enough history for the requested walk-forward folds.")

        # Anchored expanding-window folds: train on [start, split_k], test on the
        # following segment.
        tradable = timeline[self.warmup:]
        seg = len(tradable) // (self.n_folds + 1)
        report = WalkForwardReport()

        for k in range(1, self.n_folds + 1):
            train_end = tradable[seg * k - 1]
            test_start = tradable[seg * k]
            test_end = tradable[min(seg * (k + 1) - 1, len(tradable) - 1)]

            trainer = BanditTrainer(horizon=self.horizon, warmup=self.warmup)
            bandit = trainer.train(self.bars, up_to=train_end)

            bt = Backtester(
                self.bars, settings=self.s, warmup=self.warmup,
                selector=bandit, trade_start=test_start, trade_end=test_end,
            )
            res = bt.run()
            report.folds.append(FoldResult(
                train_end=train_end.isoformat(),
                test_start=test_start.isoformat(),
                test_end=test_end.isoformat(),
                total_return_pct=res.total_return_pct,
                max_drawdown_pct=res.max_drawdown_pct,
                sharpe=res.sharpe,
                num_trades=res.num_trades,
            ))
        return report


def train_bandit_from_bars(
    bars: dict[str, pd.DataFrame], horizon: int = 10, alpha: float = 0.4
) -> LinUCBSelector:
    return BanditTrainer(horizon=horizon, alpha=alpha).train(bars)
