# Capybara — Roadmap

The build is staged so that a **trustworthy, explainable baseline ships first**, and
the "smart" pieces are layered on only after the whole pipeline is validated. Each
phase keeps the module interfaces stable (especially `BrokerAdapter` and the
selector's `select()`), so upgrades are drop-in.

## Phase 1 — Autonomous baseline ✅ (this repo)

- BrokerAdapter interface + **Alpaca (paper)** and **Backtest** implementations.
- Feature engineering + **rules-based regime detection** (explainable).
- 3-strategy **playbook**: momentum, mean-reversion, breakout (long-only swing).
- **Regime → strategy selector** with performance table, hysteresis, and a
  confidence/score floor that routes to **cash**.
- **Risk manager**: per-position caps, gross exposure, max concurrent positions,
  churn control, order rate limit, and the **autonomy approval gate** (L0/L1/L2).
- **Guardrails**: daily-loss & drawdown circuit breakers + kill switch.
- **Orchestrator** control loop + state machine; broker reconciliation.
- **SQLite** state store + append-only audit log.
- **Backtester** (validation harness) with metrics + per-strategy attribution.
- **FastAPI** control plane + **Next.js/Vercel dashboard** (monitor + full HILT).

## Phase 2 — Learning selector & hardening ✅ (shipped)

- ✅ **Contextual bandit selector** (LinUCB, disjoint per-arm): context = standardized
  feature vector, arms = strategies + cash, reward = realized forward return. Trained
  offline, updatable online, drop-in behind the same `select()` API. (`selector/bandit.py`)
- ✅ **Walk-forward validation**: rolling train→test folds, strictly out-of-sample.
  (`backtest/walkforward.py`, CLI `walkforward`)
- ✅ **Backtest → selector feedback loop**: learns the Stage-1 regime→strategy score
  table from history (`backtest/attribution.py`, CLI `attribution`, `load_scores`).
- ✅ **Richer guardrails**: volatility targeting (inverse-vol sizing), per-sector
  exposure caps, and correlation-aware trimming. (`risk/exposure.py`)
- ✅ **Bracket / stop-loss orders**: attached to entries via Alpaca; simulated
  intrabar in the backtester so protective exits are validated offline.

Deferred to a later hardening pass:
- **Postgres/TimescaleDB** option for the store; Prometheus-style metrics.
- **Trade-updates WebSocket** for immediate fill events (vs. poll-based reconcile).

## Phase 3 — NLP signals & self-selected horizon ✅ (shipped)

- ✅ **News / NLP sentiment** (`data/sentiment.py`): a pluggable `SentimentProvider`
  (offline lexicon analyzer + a lazy Alpaca-news provider) scores headlines per symbol.
  A `SentimentPolicy` acts on it explainably: **veto new longs on strongly negative
  news** and **tilt position size** with the score. The bot reads the news so you
  don't have to.
- ✅ **Auto horizon selection** (`selector/horizon.py`): a `HorizonPolicy` decides
  **day-trade (intraday) vs. swing** per opportunity from volatility, momentum
  acceleration, and news catalysts. Surfaced per symbol in the dashboard.
- ✅ **Intraday data-path config** (`CAPYBARA_TIMEFRAME`): the same engine runs on a
  faster clock (1Min/5Min/15Min/1Hour) or the default daily swing clock.

Phase-3.5 follow-on: actually *route* intraday-flagged opportunities to the fast clock
automatically (dual-cadence loop) and add a transformer-based sentiment model.

## Phase 4 — analytics, alerts & ensemble ✅ (shipped)

- ✅ **Performance analytics** (`analytics/performance.py`): FIFO round-trip P&L, win
  rate, profit factor, drawdown, Sharpe, per-strategy attribution — plus a
  **plain-English summary** so you don't have to read tables. Exposed at `/api/analytics`.
- ✅ **Plain-English daily digest** (`analytics/digest.py`): a phone-friendly summary of
  what the bot did, where it stands, and what needs attention. Exposed at `/api/digest`.
- ✅ **Notifications** (`notify/`): pluggable channels — Slack/Discord/generic **webhook**
  and **email (SMTP)** — with severity filtering + dedup. Alerts on halts, kill switch,
  and orders awaiting approval, and pushes the daily digest. So you get told, instead of
  checking.
- ✅ **Ensemble allocator** (`selector/ensemble.py` + `strategies/ensemble.py`): a
  `CAPYBARA_SELECTOR=ensemble` mode that blends the whole playbook (confidence + agreement
  weighted) instead of picking one strategy.
- ✅ **Dashboard**: Analytics panel, Digest view, and a "Test alert" button.

## Phase 5 — deploy 24/7 & nudge it ✅ (shipped)

- ✅ **Runtime preferences** (`preferences.py`): pick a **risk profile**
  (conservative / balanced / aggressive) and edit the **watchlist** live from the
  dashboard — persisted in the store, applied on the next cycle. The light-touch
  "give it recommendations" surface, no redeploy needed.
- ✅ **Deployment** (`backend/Dockerfile`, `docker-compose.yml`, `backend/Procfile`,
  `docs/DEPLOYMENT.md`): run the engine on any always-on host (Docker / Railway /
  Render / Fly / VM) with the dashboard on Vercel.
- ✅ **CI** (`.github/workflows/ci.yml`): backend lint (ruff) + synthetic backtest
  smoke, and frontend production build — on every push/PR.
- ✅ **Dashboard**: Preferences panel (risk selector + watchlist editor).

## Explicitly out of scope (for now)

- **Live (real-money) trading.** Paper only until the system has a long, honest paper
  track record and the risk layer is battle-tested.
- **Shorting / leverage / options.** Long-only cash account keeps Phase 1 safe.

## Guiding principles

1. **Ship the explainable baseline first.** Trust before cleverness.
2. **Keep the seams stable** so ML upgrades are drop-in.
3. **The selector may always choose cash.** Not trading is a valid decision.
4. **Broker is the source of truth.** Reconcile, never assume.
5. **Everything is auditable.** Every decision, order, and fill is logged.
