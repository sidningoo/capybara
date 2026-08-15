"""Control-plane API (FastAPI) — the human-in-the-loop surface.

Exposes everything the dashboard needs to MONITOR (status, positions, orders,
fills, events, decisions, equity curve, strategies) and to CONTROL (pause/resume,
autonomy level, pin/block strategies, manual trade, cancel, flatten, approve/reject
queued orders, kill switch). A WebSocket at /ws streams live events.

Deployment note: this process is long-running (it owns the trading loop + broker
connection) and therefore must run on an always-on host — NOT Vercel serverless.
The Next.js dashboard talks to it over HTTP/WS.
"""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from capybara.api.schemas import (
    ApprovalReq,
    AutonomyReq,
    BlockReq,
    KillReq,
    ManualOrderReq,
    PinReq,
)
from capybara.config import Settings, get_settings
from capybara.logging_setup import get_logger
from capybara.models import Side
from capybara.orchestrator.engine import Orchestrator

log = get_logger("api")

# Module-level singleton so route handlers and the CLI share one engine.
_ORCH: Orchestrator | None = None


def build_orchestrator(settings: Settings | None = None) -> Orchestrator:
    """Construct the orchestrator. Uses Alpaca if creds exist, else a synthetic
    BacktestBroker so the dashboard/API can be explored in 'demo mode' offline."""
    s = settings or get_settings()
    if s.has_alpaca_creds:
        from capybara.broker.alpaca import AlpacaBroker
        broker = AlpacaBroker(s.alpaca_api_key, s.alpaca_secret_key, paper=s.alpaca_paper)
        log.info("API using AlpacaBroker (paper=%s).", s.alpaca_paper)
    else:
        import pandas as pd

        from capybara.broker.backtest import BacktestBroker
        from capybara.backtest.synthetic import make_universe
        bars = make_universe(s.universe_list, n_days=400)
        broker = BacktestBroker(bars, starting_cash=100_000.0)
        last_ts = max(df.index.max() for df in bars.values())
        broker.set_now(pd.Timestamp(last_ts))
        log.warning("No Alpaca creds — API in DEMO mode on synthetic data.")
    return Orchestrator(s, broker)


def get_orch() -> Orchestrator:
    global _ORCH
    if _ORCH is None:
        _ORCH = build_orchestrator()
    return _ORCH


def require_token(x_api_key: str | None = Header(default=None)) -> None:
    """Guard for mutating endpoints."""
    s = get_settings()
    if x_api_key != s.api_token:
        raise HTTPException(status_code=401, detail="invalid or missing x-api-key")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Capybara Control Plane", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def _startup() -> None:
        orch = get_orch()
        orch.bus.attach_loop(asyncio.get_running_loop())

    # ───────────── read (monitoring) ─────────────
    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "service": "capybara", "version": "0.1.0"}

    @app.get("/api/status")
    async def status(orch: Orchestrator = Depends(get_orch)) -> dict:
        return orch.snapshot()

    @app.get("/api/positions")
    async def positions(orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"positions": orch.snapshot()["positions"]}

    @app.get("/api/orders")
    async def orders(limit: int = 100, status: str | None = None,
                     orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"orders": orch.store.get_orders(limit=limit, status=status)}

    @app.get("/api/approvals")
    async def approvals(orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"pending": orch.execution.pending_approvals()}

    @app.get("/api/fills")
    async def fills(limit: int = 200, orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"fills": orch.store.get_fills(limit=limit)}

    @app.get("/api/events")
    async def events(limit: int = 200, orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"events": orch.store.get_events(limit=limit)}

    @app.get("/api/decisions")
    async def decisions(limit: int = 200, orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"decisions": orch.store.get_decisions(limit=limit)}

    @app.get("/api/equity-curve")
    async def equity_curve(orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"equity_curve": orch.store.get_equity_curve()}

    @app.get("/api/strategies")
    async def strategies(orch: Orchestrator = Depends(get_orch)) -> dict:
        pb = orch.playbook
        return {
            "playbook": [
                {"name": st.name, "suited_regimes": sorted(r.value for r in st.suited_regimes),
                 "max_weight": st.max_weight}
                for st in pb.values()
            ],
            "scores": {r.value: v for r, v in orch.selector.scores.items()},
            "pinned": orch.selector.pinned,
            "blocked": sorted(orch.selector.blocked),
        }

    # ───────────── control (mutating; token-guarded) ─────────────
    @app.post("/api/control/start", dependencies=[Depends(require_token)])
    async def ctl_start(orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.start()
        return {"state": orch.state.value}

    @app.post("/api/control/stop", dependencies=[Depends(require_token)])
    async def ctl_stop(orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.stop()
        return {"state": orch.state.value}

    @app.post("/api/control/pause", dependencies=[Depends(require_token)])
    async def ctl_pause(orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.pause()
        return {"state": orch.state.value}

    @app.post("/api/control/resume", dependencies=[Depends(require_token)])
    async def ctl_resume(orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.resume()
        return {"state": orch.state.value}

    @app.post("/api/control/clear-halt", dependencies=[Depends(require_token)])
    async def ctl_clear_halt(orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.clear_halt()
        return {"state": orch.state.value}

    @app.post("/api/control/kill", dependencies=[Depends(require_token)])
    async def ctl_kill(req: KillReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.kill_switch(flatten=req.flatten)
        return {"state": orch.state.value, "flattened": req.flatten}

    @app.post("/api/control/autonomy", dependencies=[Depends(require_token)])
    async def ctl_autonomy(req: AutonomyReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.set_autonomy_level(req.level)
        return {"autonomy_level": orch.autonomy_level}

    @app.post("/api/control/pin", dependencies=[Depends(require_token)])
    async def ctl_pin(req: PinReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.pin_strategy(req.strategy)
        return {"pinned": orch.selector.pinned}

    @app.post("/api/control/block", dependencies=[Depends(require_token)])
    async def ctl_block(req: BlockReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        orch.block_strategy(req.strategy, req.blocked)
        return {"blocked": sorted(orch.selector.blocked)}

    # ───────────── orders / positions (mutating) ─────────────
    @app.post("/api/orders/manual", dependencies=[Depends(require_token)])
    async def manual_order(req: ManualOrderReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        side = Side.BUY if req.side.lower() == "buy" else Side.SELL
        order = orch.execution.manual_order(req.symbol.upper(), side, req.qty, req.reason)
        return {"order": {"client_order_id": order.client_order_id, "status": order.status.value}}

    @app.post("/api/orders/approve", dependencies=[Depends(require_token)])
    async def approve(req: ApprovalReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        order = orch.execution.approve(req.client_order_id)
        if not order:
            raise HTTPException(404, "no such pending order")
        return {"status": order.status.value}

    @app.post("/api/orders/reject", dependencies=[Depends(require_token)])
    async def reject(req: ApprovalReq, orch: Orchestrator = Depends(get_orch)) -> dict:
        ok = orch.execution.reject(req.client_order_id)
        if not ok:
            raise HTTPException(404, "no such pending order")
        return {"rejected": True}

    @app.post("/api/orders/cancel/{broker_order_id}", dependencies=[Depends(require_token)])
    async def cancel(broker_order_id: str, orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"canceled": orch.execution.cancel(broker_order_id)}

    @app.post("/api/orders/cancel-all", dependencies=[Depends(require_token)])
    async def cancel_all(orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"canceled_count": orch.execution.cancel_all()}

    @app.post("/api/positions/{symbol}/flatten", dependencies=[Depends(require_token)])
    async def flatten(symbol: str, orch: Orchestrator = Depends(get_orch)) -> dict:
        order = orch.execution.flatten(symbol.upper())
        return {"flattened": order is not None}

    @app.post("/api/positions/flatten-all", dependencies=[Depends(require_token)])
    async def flatten_all(orch: Orchestrator = Depends(get_orch)) -> dict:
        return {"count": len(orch.execution.flatten_all())}

    # ───────────── live event stream ─────────────
    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        orch = get_orch()
        q = orch.bus.subscribe()
        try:
            await websocket.send_json({"type": "snapshot", "data": orch.snapshot()})
            while True:
                event = await q.get()
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            orch.bus.unsubscribe(q)

    return app


def serve(start_engine: bool = True) -> None:
    import uvicorn

    s = get_settings()
    global _ORCH
    _ORCH = build_orchestrator(s)
    app = create_app()
    if start_engine:
        # Start the trading loop once uvicorn's loop is up.
        @app.on_event("startup")
        async def _autostart() -> None:
            with contextlib.suppress(Exception):
                _ORCH.start()
    uvicorn.run(app, host=s.api_host, port=s.api_port, log_level="info")
