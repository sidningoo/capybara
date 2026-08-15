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

## Phase 3 — NLP signals & self-selected horizon

- **NLP / news-sentiment** features (headlines, earnings, filings) folded into the
  selector's context — the model can react to *why* a move is happening, not just the
  price pattern.
- **Auto horizon selection**: the selector decides **day-trade vs. swing** per
  opportunity, which in turn drives the data cadence and order style. This is the
  "it decides which trade is for which timeframe" capability.
- Intraday data path (minute bars, streaming) activated only when the selector picks
  a short-horizon play — the same engine, a faster clock.

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
