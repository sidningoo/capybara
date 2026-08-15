"""Execution / order manager.

The single choke-point through which every order reaches the broker — whether it
came from the autonomous loop, a human manual trade, or an approval. This is what
keeps autonomous and manual actions unified and fully audited.

Responsibilities:
  * submit NEW orders to the broker; persist + emit events
  * hold PENDING_APPROVAL orders in a queue (HILT gate) and release on approval
  * cancel orders / flatten positions on command
  * reconcile local state against the broker (broker = source of truth)
"""
from __future__ import annotations

from capybara.broker.base import BrokerAdapter
from capybara.execution.events import EventBus
from capybara.logging_setup import get_logger
from capybara.models import Fill, Order, OrderStatus, Side, utcnow
from capybara.risk.manager import RiskDecision
from capybara.store.db import Store

log = get_logger("execution")


class OrderManager:
    def __init__(self, broker: BrokerAdapter, store: Store, bus: EventBus | None = None):
        self.broker = broker
        self.store = store
        self.bus = bus or EventBus()

    # ───────────── submitting the risk decision ─────────────
    def execute_decision(self, decision: RiskDecision) -> list[Order]:
        submitted: list[Order] = []
        for order in decision.orders:
            self.store.upsert_order(order)  # persist first (NEW or PENDING_APPROVAL)
            if order.status == OrderStatus.PENDING_APPROVAL:
                self._emit("order_pending_approval", order)
                continue
            submitted.append(self._send(order))
        for sym, why in decision.skipped:
            self.store.log_event("order_skipped", {"symbol": sym, "reason": why})
        return submitted

    def _send(self, order: Order) -> Order:
        try:
            placed = self.broker.submit_order(order)
        except Exception as exc:  # pragma: no cover
            order.status = OrderStatus.REJECTED
            order.reason = (order.reason + f" | broker error: {exc}").strip(" |")
            self.store.upsert_order(order)
            self._emit("order_rejected", order)
            log.error("submit failed %s: %s", order.symbol, exc)
            return order
        self.store.upsert_order(placed)
        self._emit("order_submitted", placed)
        # Backtest broker fills immediately — record the fill.
        if placed.status == OrderStatus.FILLED and placed.filled_avg_price:
            self.store.record_fill(
                Fill(placed.symbol, placed.side, placed.filled_qty,
                     placed.filled_avg_price, placed.broker_order_id or placed.client_order_id,
                     placed.updated_at)
            )
            self._emit("order_filled", placed)
        return placed

    # ───────────── approval queue (HILT) ─────────────
    def pending_approvals(self) -> list[dict]:
        return self.store.get_orders(status=OrderStatus.PENDING_APPROVAL.value)

    def approve(self, client_order_id: str) -> Order | None:
        order = self.store.load_order(client_order_id)
        if not order or order.status != OrderStatus.PENDING_APPROVAL:
            return None
        order.status = OrderStatus.NEW
        order.reason = (order.reason + " | approved by operator").strip()
        order.updated_at = utcnow()
        self.store.upsert_order(order)
        self._emit("order_approved", order)
        return self._send(order)

    def reject(self, client_order_id: str) -> bool:
        order = self.store.load_order(client_order_id)
        if not order or order.status != OrderStatus.PENDING_APPROVAL:
            return False
        order.status = OrderStatus.CANCELED
        order.reason = (order.reason + " | rejected by operator").strip()
        order.updated_at = utcnow()
        self.store.upsert_order(order)
        self._emit("order_rejected_by_operator", order)
        return True

    # ───────────── manual actions (HILT) ─────────────
    def manual_order(self, symbol: str, side: Side, qty: float, reason: str = "manual") -> Order:
        import uuid
        order = Order(
            symbol=symbol, side=side, qty=qty, strategy="manual",
            reason=reason, client_order_id=f"cap-manual-{uuid.uuid4().hex[:12]}",
        )
        order.status = OrderStatus.NEW
        self.store.upsert_order(order)
        self._emit("manual_order", order)
        return self._send(order)

    def cancel(self, broker_order_id: str) -> bool:
        ok = self.broker.cancel_order(broker_order_id)
        self.store.log_event("order_cancel_requested", {"broker_order_id": broker_order_id, "ok": ok})
        return ok

    def cancel_all(self) -> int:
        n = self.broker.cancel_all_orders()
        self.store.log_event("cancel_all_orders", {"count": n})
        return n

    def flatten(self, symbol: str) -> Order | None:
        order = self.broker.close_position(symbol)
        self.store.log_event("flatten_position", {"symbol": symbol, "ok": order is not None})
        if order:
            self.store.upsert_order(order)
        return order

    def flatten_all(self) -> list[Order]:
        orders = self.broker.close_all_positions()
        self.store.log_event("flatten_all", {"count": len(orders)})
        for o in orders:
            self.store.upsert_order(o)
        return orders

    # ───────────── reconciliation (broker = source of truth) ─────────────
    def reconcile(self) -> dict:
        """Sync open orders + positions from the broker into the store.

        Called on startup and periodically. Prevents local state from drifting
        from reality (missed fills, restarts). Returns a summary.
        """
        open_orders = self.broker.get_open_orders()
        for o in open_orders:
            if not o.client_order_id:
                o.client_order_id = o.broker_order_id or f"reconciled-{o.symbol}"
            self.store.upsert_order(o)
        positions = self.broker.get_positions()
        summary = {"open_orders": len(open_orders), "positions": len(positions)}
        self.store.log_event("reconcile", summary)
        return summary

    def _emit(self, event_type: str, order: Order) -> None:
        payload = {
            "client_order_id": order.client_order_id,
            "broker_order_id": order.broker_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "qty": order.qty,
            "status": order.status.value,
            "strategy": order.strategy,
            "reason": order.reason,
        }
        self.store.log_event(event_type, payload)
        self.bus.publish(event_type, payload)
