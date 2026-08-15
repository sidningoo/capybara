"""Orchestrator — the autonomous control loop + state machine.

This is the brain that ties the pieces together and runs the decision cycle:

    reconcile -> read account/positions -> guardrail check -> for each symbol:
    features -> regime -> select strategy -> generate intent -> record decision
    -> risk.build_orders -> execution.execute_decision -> snapshot equity

`run_cycle()` is deliberately broker-agnostic and side-effect-contained, so the
backtester can call it bar-by-bar with a BacktestBroker, and the live loop can call
it on a timer with an AlpacaBroker — identical logic either way.

State machine: IDLE -> RUNNING <-> PAUSED, RUNNING -> HALTED (guardrail/kill),
MARKET_CLOSED while waiting for the next session. Human controls (pause/resume/
halt/kill/set level/pin/block) mutate this safely.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from capybara.broker.base import BrokerAdapter
from capybara.config import Settings
from capybara.data.market_data import MarketData
from capybara.execution.events import EventBus
from capybara.execution.order_manager import OrderManager
from capybara.logging_setup import get_logger
from capybara.models import EngineState, Intent, Regime, SignalDirection
from capybara.regime.detector import RegimeDetector
from capybara.risk.manager import RiskGuardrails, RiskManager
from capybara.selector.selector import Selection, StrategySelector
from capybara.store.db import Store
from capybara.strategies.registry import CASH, default_playbook

log = get_logger("orchestrator")


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        broker: BrokerAdapter,
        store: Store | None = None,
        bus: EventBus | None = None,
    ):
        self.s = settings
        self.broker = broker
        self.store = store or Store(settings.db_path)
        self.bus = bus or EventBus()

        self.market = MarketData(broker, timeframe="1Day", lookback=300)
        self.detector = RegimeDetector()
        self.selector = StrategySelector()
        self.playbook = default_playbook()
        self.risk = RiskManager(settings)
        self.guardrails = RiskGuardrails(
            max_daily_loss_pct=settings.max_daily_loss_pct,
            max_drawdown_pct=settings.max_drawdown_pct,
        )
        self.execution = OrderManager(broker, self.store, self.bus)

        self.state: EngineState = EngineState.IDLE
        self.autonomy_level: int = settings.autonomy_level
        self.halt_reason: str | None = None

        # last-tick snapshots (for the dashboard)
        self.last_selections: dict[str, Selection] = {}
        self.last_cycle_at: datetime | None = None
        self._current_day: str | None = None

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ───────────── clock ─────────────
    def _now(self) -> datetime:
        # BacktestBroker exposes `.now`; live uses wall clock.
        bt_now = getattr(self.broker, "now", None)
        return bt_now or datetime.now(timezone.utc)

    # ───────────── the decision cycle (used live AND in backtest) ─────────────
    def run_cycle(self) -> dict:
        now = self._now()
        self.last_cycle_at = now

        account = self.broker.get_account()
        positions = self.broker.get_positions()

        # Day boundary -> reset daily-loss baseline.
        day = now.date().isoformat()
        if self._current_day != day:
            self._current_day = day
            self.guardrails.start_day(account.equity)
            self.store.log_event("day_start", {"date": day, "equity": account.equity})

        self.guardrails.update(account.equity)
        halt, reason = self.guardrails.check(account.equity)
        if halt:
            self._enter_halt(reason or "guardrail tripped")
            self.store.record_equity(now, account.equity, account.cash)
            return {"state": self.state.value, "halted": True, "reason": reason}

        # If paused/halted, do not place new orders (but keep monitoring equity).
        if self.state in (EngineState.PAUSED, EngineState.HALTED):
            self.store.record_equity(now, account.equity, account.cash)
            return {"state": self.state.value, "halted": self.state == EngineState.HALTED}

        # 1) Features per symbol.
        symbols = self.s.universe_list
        feats = self.market.features(symbols)

        # 2) Regime -> selection -> intent, per symbol.
        intents: dict[str, Intent] = {}
        prices: dict[str, float] = {}
        for sym in symbols:
            df = feats.get(sym)
            if df is None or df.empty:
                continue
            prices[sym] = float(df["close"].iloc[-1])
            fvec = {k: float(df.iloc[-1][k]) for k in df.columns if _is_num(df.iloc[-1][k])}
            reading = self.detector.classify(sym, fvec)
            selection = self.selector.select(reading)
            self.last_selections[sym] = selection
            self.store.record_decision(
                now, sym, reading.regime.value, reading.confidence,
                selection.strategy, selection.score, selection.reason,
            )
            if selection.is_cash:
                # Exit intent (flat) so the risk manager unwinds any holding.
                intents[sym] = Intent(sym, SignalDirection.FLAT, 0.0, CASH, 0.0, selection.reason)
            else:
                strat = self.playbook.get(selection.strategy)
                intents[sym] = strat.generate(sym, df) if strat else Intent(
                    sym, SignalDirection.FLAT, 0.0, CASH, 0.0, "unknown strategy"
                )

        # 3) Also ensure held symbols outside the universe get exit intents.
        for p in positions:
            if p.symbol not in intents:
                px = self.broker.get_latest_price(p.symbol)
                if px:
                    prices[p.symbol] = px
                intents[p.symbol] = Intent(p.symbol, SignalDirection.FLAT, 0.0, CASH, 0.0, "not in universe")

        # 4) Risk -> orders -> execute.
        decision = self.risk.build_orders(account, positions, intents, prices, self.autonomy_level)
        submitted = self.execution.execute_decision(decision)

        # 5) Snapshot.
        self.store.record_equity(now, account.equity, account.cash)
        return {
            "state": self.state.value,
            "equity": account.equity,
            "orders_submitted": len(submitted),
            "orders_pending": len([o for o in decision.orders if o.status.value == "pending_approval"]),
            "intents": len(intents),
        }

    # ───────────── live loop (background thread) ─────────────
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.state = EngineState.RUNNING
        self.store.log_event("engine_start", {"autonomy_level": self.autonomy_level})
        self.execution.reconcile()
        self._thread = threading.Thread(target=self._loop, name="capybara-loop", daemon=True)
        self._thread.start()
        log.info("Orchestrator started (autonomy L%s)", self.autonomy_level)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self.state == EngineState.HALTED:
                    time.sleep(min(self.s.loop_interval_seconds, 30))
                    continue
                if not self.broker.is_market_open():
                    if self.state != EngineState.PAUSED:
                        self.state = EngineState.MARKET_CLOSED
                    time.sleep(min(self.s.loop_interval_seconds, 60))
                    continue
                if self.state == EngineState.MARKET_CLOSED:
                    self.state = EngineState.RUNNING
                if self.state == EngineState.RUNNING:
                    self.run_cycle()
            except Exception as exc:  # never let the loop die silently
                log.exception("cycle error: %s", exc)
                self.store.log_event("cycle_error", {"error": str(exc)})
            self._stop.wait(self.s.loop_interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        self.state = EngineState.IDLE
        self.store.log_event("engine_stop", {})

    # ───────────── human controls (HILT) ─────────────
    def pause(self) -> None:
        if self.state != EngineState.HALTED:
            self.state = EngineState.PAUSED
            self.store.log_event("pause", {})

    def resume(self) -> None:
        if self.state == EngineState.HALTED:
            return  # must clear_halt() explicitly
        self.state = EngineState.RUNNING
        self.store.log_event("resume", {})

    def _enter_halt(self, reason: str) -> None:
        if self.state != EngineState.HALTED:
            self.state = EngineState.HALTED
            self.halt_reason = reason
            self.store.log_event("halt", {"reason": reason})
            log.warning("HALTED: %s", reason)

    def clear_halt(self) -> None:
        """Operator explicitly clears a halt (resets daily baseline to now)."""
        self.guardrails.kill_switch = False
        self.guardrails.tripped_reason = None
        acct = self.broker.get_account()
        self.guardrails.start_day(acct.equity)
        self.halt_reason = None
        self.state = EngineState.RUNNING
        self.store.log_event("clear_halt", {})

    def kill_switch(self, flatten: bool = True) -> None:
        """Panic button: optionally flatten everything, cancel orders, and HALT."""
        self.guardrails.kill_switch = True
        if flatten:
            self.execution.cancel_all()
            self.execution.flatten_all()
        self._enter_halt("kill switch engaged")

    def set_autonomy_level(self, level: int) -> None:
        if level in (0, 1, 2):
            self.autonomy_level = level
            self.store.log_event("set_autonomy_level", {"level": level})

    def pin_strategy(self, strategy: str | None) -> None:
        self.selector.pinned = strategy
        self.store.log_event("pin_strategy", {"strategy": strategy})

    def block_strategy(self, strategy: str, blocked: bool) -> None:
        if blocked:
            self.selector.blocked.add(strategy)
        else:
            self.selector.blocked.discard(strategy)
        self.store.log_event("block_strategy", {"strategy": strategy, "blocked": blocked})

    # ───────────── snapshot for the API/dashboard ─────────────
    def snapshot(self) -> dict:
        try:
            account = self.broker.get_account()
            positions = self.broker.get_positions()
        except Exception:
            account, positions = None, []
        return {
            "state": self.state.value,
            "autonomy_level": self.autonomy_level,
            "halt_reason": self.halt_reason,
            "pinned_strategy": self.selector.pinned,
            "blocked_strategies": sorted(self.selector.blocked),
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "universe": self.s.universe_list,
            "account": _account_dict(account),
            "positions": [_pos_dict(p) for p in positions],
            "selections": {
                sym: {
                    "strategy": sel.strategy,
                    "regime": sel.regime.value,
                    "confidence": round(sel.confidence, 3),
                    "score": round(sel.score, 3),
                    "reason": sel.reason,
                }
                for sym, sel in self.last_selections.items()
            },
            "guardrails": {
                "day_start_equity": self.guardrails.day_start_equity,
                "peak_equity": self.guardrails.peak_equity,
                "kill_switch": self.guardrails.kill_switch,
                "max_daily_loss_pct": self.guardrails.max_daily_loss_pct,
                "max_drawdown_pct": self.guardrails.max_drawdown_pct,
            },
        }


def _is_num(v) -> bool:
    try:
        f = float(v)
        return f == f  # not NaN
    except (TypeError, ValueError):
        return False


def _account_dict(a) -> dict | None:
    if a is None:
        return None
    return {"equity": a.equity, "cash": a.cash, "buying_power": a.buying_power, "currency": a.currency}


def _pos_dict(p) -> dict:
    return {
        "symbol": p.symbol,
        "qty": p.qty,
        "avg_entry_price": round(p.avg_entry_price, 4),
        "current_price": round(p.current_price, 4),
        "market_value": round(p.market_value, 2),
        "unrealized_pl": round(p.unrealized_pl, 2),
        "unrealized_pl_pct": round(p.unrealized_pl_pct, 2),
    }
