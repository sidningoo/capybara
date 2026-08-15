"""A tiny thread-safe pub/sub bus for pushing live updates to the dashboard.

The orchestrator runs in a background thread; the FastAPI WebSocket handlers run
on the asyncio event loop. The bus bridges the two: `publish()` (called from any
thread) fans out to per-subscriber asyncio queues via `call_soon_threadsafe`.

In backtests no loop is attached, so publish simply records nothing extra — the
Store event log remains the durable record.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        if not self._subscribers or self._loop is None:
            return
        event = {"timestamp": datetime.utcnow().isoformat(), "type": event_type, "data": data}
        for q in list(self._subscribers):
            self._loop.call_soon_threadsafe(self._safe_put, q, event)

    @staticmethod
    def _safe_put(q: asyncio.Queue, event: dict) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop for slow consumers; Store log remains the source of truth
