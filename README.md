# 🐹 Capybara

**An autonomous Alpaca paper-trading bot that picks its own strategy based on the
market regime — with a human-in-the-loop dashboard to monitor, override, and stop it.**

Capybara is designed to be *truly hands-off*: it runs a continuous decision loop,
detects what kind of market each symbol is in, chooses the strategy best suited to
that regime, sizes positions within strict risk guardrails, and trades your Alpaca
**paper** account on its own. You come in whenever you like to review what it's
doing, change the strategy, approve or cancel orders, or hit the kill switch.

> ⚠️ **Paper trading only.** Live trading is intentionally out of scope. This is a
> research / learning system, not investment advice.

---

## Why it's structured the way it is

The hard part of an autonomous trader isn't the strategies — it's the **control
system** that lets them run unattended *safely*. Capybara resolves that with one
core rule and one core idea:

- **One rule — a strict separation of concerns:** a *strategy* only says what it
  *wants* (an `Intent`), the *risk manager* decides what's *allowed* and sizes it,
  and the *execution manager* is the only thing that talks to the broker. This is
  what makes both autonomy and human overrides safe and clean.
- **One idea — autonomy is a dial, not a switch:** you choose an autonomy *level*
  (approve-everything → auto-within-limits → full-auto). The human controls are
  always live regardless of level.

---

## Tech stack

| Layer | Technology | Why |
| --- | --- | --- |
| **Language (engine)** | **Python 3.11+** | Best ecosystem for market data, indicators, and ML; the whole quant/broker toolchain lives here. |
| **Broker + market data** | **Alpaca** via **`alpaca-py`** SDK | Commission-free US equities/ETFs, first-class **paper** trading, REST + WebSocket streams. |
| **Numerics / indicators** | **pandas**, **numpy** | Feature engineering (SMA/EMA/RSI/ATR/ADX/vol/momentum/z-score) with zero heavy native deps (no TA-Lib). |
| **Control-plane API** | **FastAPI** + **Uvicorn** | Async HTTP + WebSocket for the dashboard; typed request models. |
| **Config / models** | **pydantic** + **pydantic-settings** | One typed settings object; `.env`-driven. |
| **Persistence** | **SQLite** (stdlib) | Zero-config state store + append-only audit log. Swappable for Postgres later. |
| **Dashboard** | **Next.js 14** (App Router) · **TypeScript** · **React 18** · **Tailwind CSS** · **Recharts** | Dark trading-desk UI; deploys to **Vercel**. |
| **Packaging / tooling** | **uv**, **ruff**, **pytest** (engine); **npm** (dashboard) | Fast installs, linting, tests. |

> **Why no C++?** The workload is network-I/O bound (round-trips to Alpaca), not
> CPU bound. C++ would add complexity for no latency win at swing-trading cadence.

> **Why two deployables?** The Python engine runs a **long-lived** loop and holds a
> WebSocket — it must live on an **always-on host** (Railway / Render / Fly / a VM).
> Vercel is serverless and would kill that loop, so **only the dashboard goes to
> Vercel**. They talk over HTTP/WS.

---

## Architecture at a glance

```
┌─────────────────────────── CONTROL PLANE (human-in-the-loop) ──────────────────────────┐
│  Next.js dashboard  ──HTTP/WS──►  FastAPI  (monitor · pause/kill · pin strategy ·        │
│                                             manual trade · approve · flatten · cancel)   │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                             │
                                   ┌─────────▼──────────┐
                                   │    ORCHESTRATOR    │  control loop + state machine
                                   │  (run_cycle / loop)│  IDLE·RUNNING·PAUSED·HALTED
                                   └─────────┬──────────┘
        data → features → regime → selector → strategy → risk → execution
   ┌──────────┬───────────┬────────────┬───────────────┬───────────────┐
   │ MarketData│ Regime    │ Strategy   │ Risk /        │ Execution /   │
   │ +Features │ Detector  │ Selector   │ Portfolio Mgr │ Order Manager │
   │           │           │ + Playbook │ (guardrails)  │               │
   └──────────┴───────────┴────────────┴───────────────┴───────┬───────┘
                                                                │
                              ┌─────────────────────────────────▼──────────────────────┐
                              │  BROKER ADAPTER (interface)                              │
                              │   • AlpacaBroker   (live paper)                          │
                              │   • BacktestBroker (replays history, simulates fills)    │
                              └──────────────────────────────────────────────────────────┘
                                   +  SQLite Store (orders · fills · events · equity · decisions)
```

The **BrokerAdapter interface** is the key seam: everything above it is identical in
backtest and live, so the exact decision code is validated offline before it ever
touches the paper account.

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full breakdown.

---

## How a decision cycle works

Every tick (default: every 5 minutes while the market is open), the orchestrator:

1. **Reconciles** local state against the broker (broker = source of truth).
2. Reads account + positions; updates **guardrails** (daily-loss / drawdown circuit
   breakers). If tripped → **HALT**.
3. For each symbol in the universe: compute **features** → classify the **regime**
   (trending up/down, mean-reverting, high-vol, quiet) → the **selector** picks the
   strategy best suited to that regime (or **cash** if confidence is low).
4. The chosen **strategy** emits an `Intent` (desired target weight + rationale).
5. The **risk manager** turns intents into concrete, sized orders — enforcing
   per-position caps, gross exposure, max concurrent positions, rate limits, and the
   **autonomy approval gate**.
6. The **execution manager** sends orders (or queues large ones for your approval),
   records fills, and logs every step to the audit trail.

---

## Autonomy levels

| Level | Name | Behavior |
| --- | --- | --- |
| **L0** | Approval | Every order queues for your one-tap approval. |
| **L1** | Auto-limited *(default)* | Trades automatically within limits; unusually large orders queue for approval. |
| **L2** | Full-auto | Trades freely within the risk guardrails; you get alerts on breaches. |

Change it live from the dashboard. The kill switch and manual controls work at every
level.

---

## Quickstart

### 1) Backend (the trading engine)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or use `uv venv`
pip install -e .            # or: uv pip install -e .
cp .env.example .env        # fill in ALPACA_API_KEY / ALPACA_SECRET_KEY (paper)
```

**Run a backtest** (works offline with synthetic data — no keys needed):

```bash
python -m capybara.cli backtest --synthetic --symbols "SPY,QQQ,AAPL" --days 600
```

**Start the live paper-trading loop + control API:**

```bash
python -m capybara.cli run       # serves the API on :8000 and starts the loop
```

> With no Alpaca keys set, the API starts in **demo mode** on synthetic data so you
> can explore the dashboard without an account.

### 2) Dashboard

```bash
cd frontend
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_BASE=http://localhost:8000
npm run dev                        # http://localhost:3000
```

Paste your backend **API token** (`CAPYBARA_API_TOKEN` from `.env`) into the header
input to enable controls.

---

## Safety features

- **Circuit breakers**: auto-halt on daily-loss or drawdown limits.
- **Kill switch**: flattens all positions, cancels orders, and halts.
- **Approval gate**: large/unusual orders wait for a human at L0/L1.
- **Reconciliation**: broker state is the source of truth; survives restarts.
- **Confidence floor**: low-confidence / unknown regimes → stay in cash.
- **Append-only audit log**: every decision, order, and fill is recorded and
  answerable in the dashboard ("why did it buy X on day Y?").
- **Secrets stay out of git**: `.env` is gitignored; only `.env.example` is committed.

---

## Repository layout

```
capybara/
├── backend/            # Python trading engine + FastAPI control plane
│   └── capybara/
│       ├── broker/     # BrokerAdapter interface + Alpaca & Backtest implementations
│       ├── data/       # market data + feature engineering
│       ├── regime/     # regime detector
│       ├── strategies/ # playbook: momentum, mean-reversion, breakout
│       ├── selector/   # regime → strategy selector
│       ├── risk/       # guardrails + position sizing
│       ├── execution/  # order manager + event bus
│       ├── orchestrator/ # control loop + state machine
│       ├── store/      # SQLite state + audit log
│       ├── backtest/   # backtester + synthetic data
│       └── api/        # FastAPI app + schemas
├── frontend/           # Next.js dashboard (deploys to Vercel)
└── docs/               # ARCHITECTURE, ROADMAP, STRATEGIES
```

---

## Roadmap (the short version)

- **Phase 1 (this repo):** rules-based regime detection, 3-strategy playbook,
  regime→strategy selector, L1 autonomy, backtester, dashboard.
- **Phase 2 ✅:** **contextual-bandit (LinUCB)** selector that *learns* which strategy
  wins in which conditions, walk-forward validation, backtest→selector feedback,
  volatility-targeting + sector/correlation guardrails, and bracket/stop-loss orders.
- **Phase 3 ✅:** **news/NLP sentiment** (the bot reads headlines, vetoes trades on
  bad news, and tilts size by sentiment) and **auto horizon selection** (it decides
  day-trade vs. swing per opportunity). Surfaced in the dashboard.

Full detail in **[docs/ROADMAP.md](docs/ROADMAP.md)**.

---

## License

MIT.
