"""Risk & portfolio manager.

This is the ONLY component allowed to turn desires into orders. It owns every
portfolio-level decision, which is what makes autonomy safe and human overrides
clean:

  * Guardrails (RiskGuardrails): daily-loss and drawdown circuit breakers +
    kill switch. When tripped, the orchestrator moves to HALTED.
  * Sizing / limits (RiskManager): converts strategy Intents (target weights)
    into concrete buy/sell Orders while enforcing per-position caps, gross
    exposure, max concurrent positions, order rate limits, and the autonomy
    approval gate (orders that are too large, or any order at level 0, are
    marked PENDING_APPROVAL instead of being sent).
"""
from __future__ import annotations

import math
import uuid
from collections import deque
from dataclasses import dataclass, field

from capybara.config import Settings
from capybara.logging_setup import get_logger
from capybara.models import (
    Account,
    AutonomyLevel,
    Intent,
    Order,
    OrderStatus,
    Position,
    Side,
    SignalDirection,
    utcnow,
)

log = get_logger("risk")


# ───────────────────────── Guardrails / circuit breakers ─────────────────────────
@dataclass
class RiskGuardrails:
    max_daily_loss_pct: float
    max_drawdown_pct: float
    day_start_equity: float | None = None
    peak_equity: float | None = None
    kill_switch: bool = False
    tripped_reason: str | None = None

    def start_day(self, equity: float) -> None:
        self.day_start_equity = equity
        if self.peak_equity is None:
            self.peak_equity = equity

    def update(self, equity: float) -> None:
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    def check(self, equity: float) -> tuple[bool, str | None]:
        """Return (halt, reason). Halt if any breaker is tripped."""
        if self.kill_switch:
            return True, "kill switch engaged"
        if self.day_start_equity:
            daily_loss = (self.day_start_equity - equity) / self.day_start_equity * 100
            if daily_loss >= self.max_daily_loss_pct:
                self.tripped_reason = f"daily loss {daily_loss:.2f}% >= {self.max_daily_loss_pct}%"
                return True, self.tripped_reason
        if self.peak_equity:
            dd = (self.peak_equity - equity) / self.peak_equity * 100
            if dd >= self.max_drawdown_pct:
                self.tripped_reason = f"drawdown {dd:.2f}% >= {self.max_drawdown_pct}%"
                return True, self.tripped_reason
        return False, None


# ───────────────────────── Sizing / order construction ─────────────────────────
@dataclass
class RiskDecision:
    orders: list[Order] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (symbol, reason)
    notes: list[str] = field(default_factory=list)


class RiskManager:
    def __init__(self, settings: Settings):
        self.s = settings
        # rate limiter: timestamps of recently emitted orders
        self._recent_order_ts: deque = deque(maxlen=500)
        # churn control: don't rebalance for tiny deltas
        self.rebalance_threshold_pct = 0.02  # 2% of equity min delta to act

    def build_orders(
        self,
        account: Account,
        positions: list[Position],
        intents: dict[str, Intent],
        prices: dict[str, float],
        autonomy_level: int,
    ) -> RiskDecision:
        decision = RiskDecision()
        equity = account.equity
        if equity <= 0:
            decision.notes.append("no equity; skipping")
            return decision

        pos_by_symbol = {p.symbol: p for p in positions}

        # 1) Desired target weights from LONG intents (FLAT/SHORT -> 0 for now).
        targets: dict[str, float] = {}
        for sym, intent in intents.items():
            if intent.direction == SignalDirection.LONG and intent.target_weight > 0:
                targets[sym] = min(intent.target_weight, self.s.max_position_pct / 100.0)
            else:
                targets[sym] = 0.0

        # 2) Enforce max concurrent positions — keep the highest-confidence targets.
        desired = {s: w for s, w in targets.items() if w > 0}
        if len(desired) > self.s.max_concurrent_positions:
            ranked = sorted(
                desired.keys(),
                key=lambda s: intents[s].confidence,
                reverse=True,
            )
            keep = set(ranked[: self.s.max_concurrent_positions])
            for s in list(desired.keys()):
                if s not in keep:
                    targets[s] = 0.0
                    decision.skipped.append((s, "max concurrent positions reached"))

        # 3) Enforce gross exposure cap — scale all targets down proportionally.
        gross = sum(w for w in targets.values() if w > 0)
        cap = self.s.max_gross_exposure_pct / 100.0
        if gross > cap and gross > 0:
            scale = cap / gross
            targets = {s: (w * scale if w > 0 else 0.0) for s, w in targets.items()}
            decision.notes.append(f"scaled targets by {scale:.2f} to respect gross exposure cap")

        # 4) Convert target weights into orders (delta vs current holdings).
        #    Include held symbols not in intents so we can exit them (target 0).
        all_symbols = set(targets) | set(pos_by_symbol)
        rate_budget = self._rate_budget()

        for sym in sorted(all_symbols):
            price = prices.get(sym)
            if not price or price <= 0:
                decision.skipped.append((sym, "no price"))
                continue
            target_w = targets.get(sym, 0.0)
            target_shares = math.floor((target_w * equity) / price)
            current_shares = int(pos_by_symbol[sym].qty) if sym in pos_by_symbol else 0
            delta = target_shares - current_shares
            if delta == 0:
                continue

            delta_value = abs(delta) * price
            # Churn control: ignore tiny rebalances (but always allow full exits).
            if target_shares > 0 and delta_value < self.rebalance_threshold_pct * equity:
                continue

            if rate_budget <= 0:
                decision.skipped.append((sym, "order rate limit reached this window"))
                continue

            side = Side.BUY if delta > 0 else Side.SELL
            intent = intents.get(sym)
            order = Order(
                symbol=sym,
                side=side,
                qty=abs(delta),
                strategy=intent.strategy if intent else "exit",
                reason=(intent.reason if intent else "exit position (no active intent)"),
                client_order_id=f"cap-{uuid.uuid4().hex[:16]}",
            )
            order.status = self._gate(order, delta_value, autonomy_level)
            decision.orders.append(order)
            rate_budget -= 1
            self._recent_order_ts.append(utcnow())

        return decision

    # ── autonomy approval gate ──
    def _gate(self, order: Order, notional: float, autonomy_level: int) -> OrderStatus:
        if autonomy_level == AutonomyLevel.APPROVAL:
            order.reason = (order.reason + " | queued: approval mode (L0)").strip()
            return OrderStatus.PENDING_APPROVAL
        if autonomy_level == AutonomyLevel.AUTO_LIMITED and notional > self.s.approval_order_notional:
            order.reason = (
                order.reason + f" | queued: notional ${notional:,.0f} > ${self.s.approval_order_notional:,.0f} (L1)"
            ).strip()
            return OrderStatus.PENDING_APPROVAL
        return OrderStatus.NEW

    # ── order rate limiter ──
    def _rate_budget(self) -> int:
        now = utcnow()
        while self._recent_order_ts and (now - self._recent_order_ts[0]).total_seconds() > 60:
            self._recent_order_ts.popleft()
        return max(0, self.s.max_orders_per_min - len(self._recent_order_ts))
