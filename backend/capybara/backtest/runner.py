"""Backtester — replays historical bars through the REAL decision stack.

It constructs a BacktestBroker + an Orchestrator (same class used live) and steps
the clock bar-by-bar, calling `run_cycle()` each step. Because the orchestrator is
broker-agnostic, whatever it does here is exactly what it will do against the paper
account — this is the validation harness.

Also computes standard performance metrics and a per-strategy attribution table
that can be fed back into the selector (`StrategySelector.load_scores`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from capybara.broker.backtest import BacktestBroker
from capybara.config import Settings, get_settings
from capybara.logging_setup import get_logger
from capybara.models import EngineState
from capybara.orchestrator.engine import Orchestrator
from capybara.store.db import Store

log = get_logger("backtest")


@dataclass
class BacktestResult:
    starting_equity: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float
    num_trades: int
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    per_strategy_fills: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"start=${self.starting_equity:,.0f} final=${self.final_equity:,.0f} "
            f"ret={self.total_return_pct:+.2f}% CAGR={self.cagr_pct:+.2f}% "
            f"maxDD={self.max_drawdown_pct:.2f}% Sharpe={self.sharpe:.2f} "
            f"trades={self.num_trades}"
        )


class Backtester:
    def __init__(
        self,
        bars: dict[str, pd.DataFrame],
        settings: Settings | None = None,
        starting_cash: float = 100_000.0,
        warmup: int = 210,
        slippage_bps: float = 1.0,
        commission_per_share: float = 0.0,
        selector=None,
        trade_start=None,
        trade_end=None,
    ):
        self.bars = bars
        self.s = settings or get_settings()
        self.starting_cash = starting_cash
        self.warmup = warmup
        self.trade_start = trade_start
        self.trade_end = trade_end
        self.broker = BacktestBroker(
            bars, starting_cash=starting_cash,
            slippage_bps=slippage_bps, commission_per_share=commission_per_share,
        )
        # In-memory store so backtests don't pollute the live DB.
        self.store = Store(":memory:")
        self.orch = Orchestrator(self.s, self.broker, store=self.store)
        # Optionally inject a pre-trained/alternative selector (e.g., LinUCB).
        if selector is not None:
            self.orch.selector = selector
        # Backtests run fully autonomous (no human approval queue).
        self.orch.autonomy_level = 2
        self.orch.state = EngineState.RUNNING

    def run(self) -> BacktestResult:
        # Union of all timestamps across symbols, sorted.
        timeline = sorted({ts for df in self.bars.values() for ts in df.index})
        if len(timeline) <= self.warmup:
            raise ValueError(f"Not enough bars ({len(timeline)}) for warmup {self.warmup}")

        equity_curve: list[tuple[str, float]] = []
        for ts in timeline[self.warmup:]:
            # Restrict the *trading* window (broker still only sees data <= now).
            if self.trade_start is not None and ts < self.trade_start:
                self.broker.set_now(ts)
                continue
            if self.trade_end is not None and ts > self.trade_end:
                break
            self.broker.set_now(ts)
            self.orch.run_cycle()
            eq = self.broker.get_account().equity
            equity_curve.append((ts.isoformat(), eq))

        return self._metrics(equity_curve)

    def _metrics(self, equity_curve: list[tuple[str, float]]) -> BacktestResult:
        eqs = np.array([e for _, e in equity_curve], dtype=float)
        start = self.starting_cash
        final = float(eqs[-1]) if len(eqs) else start
        total_return = (final / start - 1) * 100

        # Drawdown
        peak = np.maximum.accumulate(eqs) if len(eqs) else np.array([start])
        dd = (peak - eqs) / peak if len(eqs) else np.array([0.0])
        max_dd = float(np.max(dd) * 100) if len(dd) else 0.0

        # Daily returns -> Sharpe (rf=0)
        rets = np.diff(eqs) / eqs[:-1] if len(eqs) > 1 else np.array([0.0])
        sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252)) if np.std(rets) > 0 else 0.0

        # CAGR
        n_days = max(1, len(eqs))
        years = n_days / 252
        cagr = ((final / start) ** (1 / years) - 1) * 100 if final > 0 and years > 0 else 0.0

        # Per-strategy fill attribution.
        per_strat: dict[str, int] = {}
        for f in self.broker.fills:
            order = self.broker.get_order(f.order_id)
            key = order.strategy if order else "unknown"
            per_strat[key] = per_strat.get(key, 0) + 1

        return BacktestResult(
            starting_equity=start,
            final_equity=final,
            total_return_pct=total_return,
            cagr_pct=cagr,
            max_drawdown_pct=max_dd,
            sharpe=sharpe,
            num_trades=len(self.broker.fills),
            equity_curve=equity_curve,
            per_strategy_fills=per_strat,
        )
