# Capybara — Architecture

This document explains how the system is put together and *why*. The guiding
principle: the difficulty in an autonomous trader is the **control system**, not the
strategies. Every design choice below serves safe, unattended operation with clean
human override.

## The one rule: separation of concerns

```
Strategy  →  Intent   (what I WANT: a target weight + rationale)
RiskMgr   →  Order    (what is ALLOWED: sized within portfolio limits)
Execution →  Broker   (the ONLY thing that places/cancels orders)
```

- A **Strategy** is a pure function of `(symbol, feature frame) → Intent`. It never
  reads account size, never knows other positions, never touches the broker. It only
  expresses conviction.
- The **RiskManager** owns *all* portfolio-level decisions: per-position caps, gross
  exposure, max concurrent positions, churn control, order rate limits, and the
  autonomy approval gate. It converts intents into concrete buy/sell orders.
- The **OrderManager** (execution) is the single choke-point to the broker. Whether
  an order originates from the autonomous loop, a human manual trade, or an approval,
  it flows through the same path and is audited identically.

This separation is what lets the selector swap strategies freely, lets a human
override without fighting a strategy's internal state, and keeps autonomous and
manual actions unified.

## The key seam: BrokerAdapter

`broker/base.py` defines an abstract `BrokerAdapter`. Two implementations satisfy it:

- **`AlpacaBroker`** — live paper trading (REST orders/account + market data). The
  `alpaca-py` SDK is imported lazily, so the rest of the system runs without it.
- **`BacktestBroker`** — replays historical bars and simulates fills with slippage /
  commission, long-only cash account, **no lookahead** (only returns data with
  `timestamp <= now`).

Because everything above this interface is broker-agnostic, the **exact same**
decision stack runs in backtest and live. The backtester *is* the validation harness.

## Components

| Component | File | Responsibility |
| --- | --- | --- |
| Config | `config.py` | One typed `Settings` object from env/`.env`. |
| Domain models | `models.py` | `Bar`, `Regime`, `Intent`, `Order`, `Position`, `Account`, `EngineState`, `AutonomyLevel`. Plain dataclasses (cheap in hot loops). |
| Market data | `data/market_data.py` | Fetches bars via broker, enriches with features. |
| Features | `data/features.py` | Pure pandas/numpy indicators (SMA/EMA/RSI/ATR/ADX/vol/momentum/z-score/Donchian). |
| Regime detector | `regime/detector.py` | Feature vector → interpretable `Regime` + confidence. |
| Strategies | `strategies/` | `momentum`, `mean_reversion`, `breakout`; each declares its `suited_regimes`. |
| Selector | `selector/selector.py` | Regime → best strategy via a performance table, with hysteresis + confidence/score floors → cash. |
| Risk | `risk/manager.py` | `RiskGuardrails` (circuit breakers) + `RiskManager` (sizing + gating). |
| Execution | `execution/order_manager.py` | Sends/queues orders, approvals, cancel/flatten, reconciliation. |
| Event bus | `execution/events.py` | Thread-safe pub/sub bridging the loop thread → API WebSocket. |
| Store | `store/db.py` | SQLite: orders, fills, **append-only events**, equity curve, decisions. |
| Orchestrator | `orchestrator/engine.py` | The control loop + state machine; wires it all together. |
| Backtester | `backtest/runner.py` | Steps the clock bar-by-bar through `run_cycle()`; computes metrics + per-strategy attribution. |
| API | `api/app.py` | FastAPI control plane + `/ws` live feed. |

## The control loop & state machine

`Orchestrator.run_cycle()` is deliberately broker-agnostic and side-effect-contained,
so the backtester calls it bar-by-bar and the live loop calls it on a timer —
identical logic.

**States:** `IDLE → RUNNING ⇄ PAUSED`, `RUNNING → HALTED` (guardrail/kill), and
`MARKET_CLOSED` while waiting for the next session.

**Each cycle:**
1. Reconcile with broker (source of truth).
2. Account/positions → guardrail check → HALT if tripped.
3. Per symbol: features → regime → selection → intent (or FLAT if cash) → record decision.
4. Also emit exit intents for any held symbol no longer in the universe.
5. `risk.build_orders(...)` → `execution.execute_decision(...)`.
6. Snapshot equity.

**Why broker-as-source-of-truth matters:** the #1 killer of unattended bots is local
state drifting from reality (a missed fill, a restart). On startup and periodically,
Capybara reconciles against Alpaca and corrects itself.

## Human-in-the-loop (HILT)

The FastAPI control plane exposes:

- **Monitor:** status, positions, orders, fills, events, decisions, equity curve, strategies.
- **Control:** start/stop/pause/resume, autonomy level, pin/block a strategy, kill switch, clear-halt.
- **Act:** manual trade, approve/reject queued orders, cancel order, flatten position/all.

All mutating endpoints require an `x-api-key`. Manual actions flow through the same
risk/execution path as autonomous ones, so overrides and the bot's own decisions are
unified and equally audited.

## Data flow to the dashboard

The orchestrator runs in a background thread; FastAPI runs on the asyncio loop. The
`EventBus` bridges them: `publish()` (any thread) fans out to per-subscriber asyncio
queues via `call_soon_threadsafe`, which the `/ws` handler forwards to the browser.
The SQLite event log remains the durable record if a client is slow or disconnected.

## Phase 2 additions (learning selector & risk hardening)

| Component | File | Responsibility |
| --- | --- | --- |
| Context scaler | `selector/context.py` | Fixed feature list + standardization; the model's input vector. |
| Bandit selector | `selector/bandit.py` | LinUCB (disjoint per-arm) with a cash baseline; same `select()` API as the rules selector, so it's swappable via `CAPYBARA_SELECTOR`. |
| Trainer + walk-forward | `backtest/walkforward.py` | Off-policy offline training from realized forward returns; rolling out-of-sample validation. |
| Attribution | `backtest/attribution.py` | Learns the Stage-1 regime→strategy score table from history (`load_scores`). |
| Exposure controls | `risk/exposure.py` | Sector map, inverse-vol sizing, sector caps, correlation trimming — applied inside `RiskManager.build_orders`. |
| Brackets | `models.py` / `broker/*` | `OrderClass.BRACKET` with stop-loss + take-profit; Alpaca native + simulated intrabar in the backtester. |

**Selector interface stability:** both `StrategySelector` (rules) and `LinUCBSelector`
(learned) expose `select(reading) -> Selection`, plus `pinned` / `blocked`. The
orchestrator's `_build_selector()` picks one from config; nothing downstream changes.
This is the "keep the seams stable so ML upgrades are drop-in" principle in action.

## Phase 3 additions (news sentiment & auto horizon)

| Component | File | Responsibility |
| --- | --- | --- |
| Sentiment | `data/sentiment.py` | `SentimentAnalyzer` (dependency-free finance lexicon w/ negation), `SentimentProvider` (Null offline + lazy Alpaca-news), and `SentimentPolicy` (veto new longs on bad news, tilt size by score). |
| Horizon | `selector/horizon.py` | `HorizonPolicy` decides intraday vs. swing per symbol from volatility, momentum acceleration, and news catalysts. |

**Where they plug in:** the orchestrator fetches sentiment once per cycle, computes a
horizon per symbol, attaches both to the `Selection` (shown in the UI + logged), and
runs the `SentimentPolicy` over the intents *before* the risk manager sizes them — so
news affects behavior through the same intent→risk→execution path as everything else.
Sentiment is a portfolio/selector-level signal, deliberately kept out of the bandit's
trained context to avoid a train/live feature mismatch (documented in the roadmap).
The data cadence is configurable via `CAPYBARA_TIMEFRAME` (swing daily bars by default).

## Phase 4 additions (analytics, alerts & ensemble)

| Component | File | Responsibility |
| --- | --- | --- |
| Analytics | `analytics/performance.py` | FIFO round-trip P&L, win rate, profit factor, drawdown, Sharpe, per-strategy attribution + a plain-English summary. From the store, so it works for live and backtest alike. |
| Daily digest | `analytics/digest.py` | Phone-friendly plain-English recap of the day's activity + current stance + what needs attention. |
| Notifications | `notify/` | `Notifier` ABC, `WebhookNotifier` (Slack/Discord/generic), `EmailNotifier` (SMTP), and `NotificationManager` (level filter + dedup + digest). |
| Ensemble | `selector/ensemble.py`, `strategies/ensemble.py` | A selector mode that blends the whole playbook (confidence + agreement weighted) into one position. |

**Notifications wiring:** the orchestrator holds a `NotificationManager` and fires
alerts on halt, kill switch, and pending approvals, and sends the daily digest at the
day rollover — all best-effort and wrapped so a failing channel never touches the
trading loop. This is the piece that makes the system *actually* hands-off: the user is
pushed a summary and told when something needs a look, instead of having to watch.

Exposed via `GET /api/analytics`, `GET /api/digest`, and `POST /api/notify/test`.

## Deployment topology

```
[ Browser ] ──► [ Next.js dashboard on Vercel ] ──HTTP/WS──► [ Python engine+API on an always-on host ] ──► [ Alpaca paper ]
```

The engine **cannot** run on Vercel (serverless kills the long-lived loop + WebSocket).
Host it on Railway/Render/Fly/a VM; point the dashboard's `NEXT_PUBLIC_API_BASE` at
its public HTTPS URL and allow CORS from the Vercel domain.
