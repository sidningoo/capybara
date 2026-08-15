# Capybara — Backend (trading engine + control API)

The Python engine that detects the market regime, selects a strategy, sizes trades
within risk guardrails, and trades an Alpaca **paper** account autonomously — plus a
FastAPI control plane for the dashboard.

See the top-level [`README.md`](../README.md) and [`docs/`](../docs) for the full
picture. Quick reference:

## Install

```bash
python -m venv .venv && source .venv/bin/activate   # or: uv venv && source .venv/bin/activate
pip install -e .            # or: uv pip install -e .
cp .env.example .env        # add ALPACA_API_KEY / ALPACA_SECRET_KEY (paper)
```

## Commands

```bash
# Backtest on synthetic data (no keys/network needed) — validates the full pipeline
python -m capybara.cli backtest --synthetic --symbols "SPY,QQQ,AAPL" --days 600

# Backtest on real Alpaca historical data (needs paper keys)
python -m capybara.cli backtest --symbols "SPY,QQQ" --days 500

# Start the live paper-trading loop + control API on :8000
python -m capybara.cli run

# Start ONLY the control API (no trading loop)
python -m capybara.cli api
```

## Configuration

All settings come from environment variables / `.env` (see `.env.example` and
`capybara/config.py`): Alpaca keys, universe, autonomy level, loop interval, risk
guardrails, DB path, API host/port/CORS, and the API token.

## Package layout

```
capybara/
├── config.py            # typed Settings (pydantic-settings)
├── models.py            # domain models
├── broker/              # BrokerAdapter + Alpaca / Backtest
├── data/                # market data + features
├── regime/              # regime detector
├── strategies/          # momentum, mean_reversion, breakout, registry
├── selector/            # regime → strategy selector
├── risk/                # guardrails + sizing
├── execution/           # order manager + event bus
├── orchestrator/        # control loop + state machine
├── store/               # SQLite state + audit log
├── backtest/            # backtester + synthetic data
├── api/                 # FastAPI app + schemas
└── cli.py               # entry point
```

## Notes

- `alpaca-py` is imported lazily, so backtests and unit tests run without it.
- The engine is long-running and holds a WebSocket — deploy on an **always-on host**,
  not Vercel.
