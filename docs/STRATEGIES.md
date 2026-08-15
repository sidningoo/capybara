# Capybara — Strategies & the Selector

## Mental model

Capybara separates **"which strategy should be active right now?"** (the *selector*,
driven by the market **regime**) from **"given that strategy, what should I do with
this symbol?"** (the *strategy* itself). Each strategy is designed to exploit a
specific regime; the selector routes each symbol to the right one.

## Regimes

`regime/detector.py` classifies each symbol into an interpretable label plus a
confidence, using ADX (trend strength), realized volatility, momentum, and
price-vs-moving-average position:

| Regime | Roughly means | Favored strategy |
| --- | --- | --- |
| `TRENDING_UP` | Strong up-trend (high ADX, price > SMA50, +momentum) | momentum / breakout |
| `TRENDING_DOWN` | Strong down-trend | cash (long-only book) |
| `MEAN_REVERTING` | Choppy / range-bound (low ADX) | mean-reversion |
| `HIGH_VOLATILITY` | Elevated realized vol (risk-off) | breakout (reduced) / cash |
| `QUIET` | Very low movement | mean-reversion (light) |
| `UNKNOWN` | Not enough history / ambiguous | **cash** |

Stage 1 is rules-based on purpose: every decision is explainable in the dashboard
("chose momentum because ADX=31, price>SMA50, 20d momentum=+6%").

## The playbook (Phase 1)

All are **long-only swing** strategies. Each emits an `Intent` with a target weight
(conviction) and a human-readable reason; the risk manager does the sizing.

### 1. Momentum (`momentum`) — the anchor
- **Thesis:** trends persist over days-to-weeks.
- **Enter long** when price > 50-day SMA, 20-day momentum ≥ 2%, and MACD > signal —
  unless RSI is already extremely overbought (≥ 80).
- **Exit** when the trend breaks (price < SMA50) or momentum rolls over.
- **Best in:** `TRENDING_UP`.

### 2. Mean-reversion (`mean_reversion`)
- **Thesis:** in range-bound markets, extreme short-term moves revert.
- **Enter long** when the 20-day z-score ≤ −1.5 and RSI ≤ 35 — but only while price is
  above the 200-day SMA (buy dips in healthy names, not falling knives).
- **Exit** once price reverts back toward the mean (z ≥ −0.2).
- **Best in:** `MEAN_REVERTING`, tolerable in `QUIET`.

### 3. Breakout (`breakout`) — Donchian-style trend-following
- **Thesis:** a close above the recent range high often starts a new leg.
- **Enter long** when price closes ≥ the prior bar's 20-day high and is above SMA50.
- **Exit** when price closes back below the 20-day SMA.
- **Best in:** `TRENDING_UP` and the start of `HIGH_VOLATILITY` expansions.

## The selector

`selector/selector.py` chooses per symbol from a **performance table**
`scores[regime][strategy] → expected score (0..1)`, seeded with sensible priors and
overwritable from backtest attribution (`load_scores`).

Three safety behaviours:
1. **Confidence floor** — `UNKNOWN` regime or confidence below threshold → **cash**.
2. **Score floor** — if even the best strategy scores poorly (e.g., everything is bad
   in a downtrend for a long-only book) → **cash**.
3. **Hysteresis** — don't switch away from the current strategy unless a challenger
   beats it by a margin. Prevents whipsaw flip-flopping.

**HILT overrides:** an operator can **pin** a strategy (force it) or **block** one
(never select it) from the dashboard.

> **Cash is a position.** The selector is explicitly allowed to choose *not* to trade.
> This is often the correct decision and a key safety property.

## Adding a strategy

1. Subclass `Strategy` in `strategies/`, set `name`, `suited_regimes`, `max_weight`,
   and implement `generate(symbol, feats) → Intent`.
2. Register it in `strategies/registry.py::default_playbook()`.
3. Add its priors to `selector/selector.py::DEFAULT_SCORES` per regime.
4. Backtest to refine the score table.

## How the selector will evolve (Phases 2–3)

- **Phase 2 — contextual bandit:** replace the static score table with an online
  learner (LinUCB / Thompson sampling) whose *context* is the feature vector and
  whose *reward* is realized risk-adjusted P&L. It adapts as conditions change while
  keeping the same `select()` interface. Priors seeded from backtests.
- **Phase 3 — NLP + auto-horizon:** fold news/sentiment features into the context,
  and let the selector also decide the **time horizon** (day-trade vs. swing) per
  opportunity, not just the strategy.
