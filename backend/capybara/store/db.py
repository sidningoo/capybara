"""Persistence: SQLite state store + append-only event log.

Zero-config (a single .db file). Everything the dashboard shows and every audit
question ("why did it trade X on day Y?") is answerable from here. Postgres can be
swapped in later behind the same method surface.

Design notes:
  * The `events` table is append-only — it is the audit trail. Never updated.
  * `orders` is the mutable current view (status changes as fills arrive).
  * Thread-safe via a single connection + lock (check_same_thread=False).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any

from capybara.logging_setup import get_logger
from capybara.models import Fill, Order, OrderClass, OrderStatus, OrderType, Side, TimeInForce

log = get_logger("store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    client_order_id TEXT PRIMARY KEY,
    broker_order_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    order_type TEXT NOT NULL,
    time_in_force TEXT NOT NULL,
    limit_price REAL,
    status TEXT NOT NULL,
    filled_qty REAL DEFAULT 0,
    filled_avg_price REAL,
    strategy TEXT,
    reason TEXT,
    order_class TEXT DEFAULT 'simple',
    stop_loss_price REAL,
    take_profit_price REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    price REAL NOT NULL,
    order_id TEXT,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equity_curve (
    timestamp TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    cash REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    regime TEXT,
    confidence REAL,
    strategy TEXT,
    score REAL,
    reason TEXT,
    sentiment REAL DEFAULT 0,
    horizon TEXT DEFAULT 'swing'
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
"""


class Store:
    def __init__(self, path: str = "./capybara.db"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()
        log.info("Store ready at %s", path)

    def _migrate(self) -> None:
        """Best-effort additive migrations for pre-existing databases."""
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(orders)").fetchall()}
        for name, decl in (
            ("order_class", "TEXT DEFAULT 'simple'"),
            ("stop_loss_price", "REAL"),
            ("take_profit_price", "REAL"),
        ):
            if name not in cols:
                self._conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {decl}")
        dcols = {r[1] for r in self._conn.execute("PRAGMA table_info(decisions)").fetchall()}
        for name, decl in (("sentiment", "REAL DEFAULT 0"), ("horizon", "TEXT DEFAULT 'swing'")):
            if name not in dcols:
                self._conn.execute(f"ALTER TABLE decisions ADD COLUMN {name} {decl}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ───────────── events (append-only audit log) ─────────────
    def log_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(timestamp, type, data) VALUES (?,?,?)",
                (datetime.utcnow().isoformat(), event_type, json.dumps(data or {}, default=str)),
            )
            self._conn.commit()

    def get_events(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, type, data FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"timestamp": r["timestamp"], "type": r["type"], "data": json.loads(r["data"])} for r in rows]

    # ───────────── orders ─────────────
    def upsert_order(self, order: Order) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO orders(client_order_id, broker_order_id, symbol, side, qty,
                        order_type, time_in_force, limit_price, status, filled_qty,
                        filled_avg_price, strategy, reason, order_class, stop_loss_price,
                        take_profit_price, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(client_order_id) DO UPDATE SET
                        broker_order_id=excluded.broker_order_id,
                        status=excluded.status,
                        filled_qty=excluded.filled_qty,
                        filled_avg_price=excluded.filled_avg_price,
                        qty=excluded.qty,
                        reason=excluded.reason,
                        updated_at=excluded.updated_at""",
                (
                    order.client_order_id, order.broker_order_id, order.symbol, order.side.value,
                    order.qty, order.order_type.value, order.time_in_force.value, order.limit_price,
                    order.status.value, order.filled_qty, order.filled_avg_price, order.strategy,
                    order.reason, order.order_class.value, order.stop_loss_price,
                    order.take_profit_price, order.created_at.isoformat(), order.updated_at.isoformat(),
                ),
            )
            self._conn.commit()

    def get_orders(self, limit: int = 100, status: str | None = None) -> list[dict]:
        q = "SELECT * FROM orders"
        params: tuple = ()
        if status:
            q += " WHERE status = ?"
            params = (status,)
        q += " ORDER BY created_at DESC LIMIT ?"
        params += (limit,)
        with self._lock:
            rows = self._conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def get_order(self, client_order_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute(
                "SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)
            ).fetchone()
        return dict(r) if r else None

    def load_order(self, client_order_id: str) -> Order | None:
        d = self.get_order(client_order_id)
        if not d:
            return None
        return Order(
            symbol=d["symbol"],
            side=Side(d["side"]),
            qty=d["qty"],
            order_type=OrderType(d["order_type"]),
            time_in_force=TimeInForce(d["time_in_force"]),
            limit_price=d["limit_price"],
            status=OrderStatus(d["status"]),
            filled_qty=d["filled_qty"] or 0.0,
            filled_avg_price=d["filled_avg_price"],
            strategy=d["strategy"] or "manual",
            reason=d["reason"] or "",
            order_class=OrderClass(d["order_class"] or "simple"),
            stop_loss_price=d["stop_loss_price"],
            take_profit_price=d["take_profit_price"],
            client_order_id=d["client_order_id"],
            broker_order_id=d["broker_order_id"],
        )

    # ───────────── fills ─────────────
    def record_fill(self, fill: Fill) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO fills(symbol, side, qty, price, order_id, timestamp) VALUES (?,?,?,?,?,?)",
                (fill.symbol, fill.side.value, fill.qty, fill.price, fill.order_id, fill.timestamp.isoformat()),
            )
            self._conn.commit()

    def get_fills(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM fills ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ───────────── equity curve ─────────────
    def record_equity(self, ts: datetime, equity: float, cash: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO equity_curve(timestamp, equity, cash) VALUES (?,?,?)",
                (ts.isoformat(), equity, cash),
            )
            self._conn.commit()

    def get_equity_curve(self, limit: int = 1000) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM equity_curve ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ───────────── decisions (regime + selection log) ─────────────
    def record_decision(
        self, ts: datetime, symbol: str, regime: str, confidence: float,
        strategy: str, score: float, reason: str,
        sentiment: float = 0.0, horizon: str = "swing",
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO decisions(timestamp, symbol, regime, confidence, strategy,
                        score, reason, sentiment, horizon)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (ts.isoformat(), symbol, regime, confidence, strategy, score, reason,
                 sentiment, horizon),
            )
            self._conn.commit()

    def get_decisions(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ───────────── key-value store (preferences etc.) ─────────────
    def set_kv(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv(key, value, updated_at) VALUES (?,?,?)",
                (key, json.dumps(value, default=str), datetime.utcnow().isoformat()),
            )
            self._conn.commit()

    def get_kv(self, key: str, default: Any = None) -> Any:
        with self._lock:
            r = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default
