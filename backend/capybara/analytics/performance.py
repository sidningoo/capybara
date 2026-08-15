"""Performance analytics — answers "how am I doing?" from the store.

Computes portfolio metrics (return, drawdown, Sharpe), realized round-trip trade
stats (win rate, avg win/loss, profit factor), and per-strategy attribution, then
renders a **plain-English summary**. The plain-English part matters: a hands-off user
should be able to understand performance at a glance without reading tables.

Everything is derived from the append-only store (equity curve + fills + decisions),
so it works identically for live and backtest data.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field

import numpy as np

from capybara.store.db import Store


@dataclass
class TradeStat:
    strategy: str
    round_trips: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    @property
    def win_rate(self) -> float:
        return (self.wins / self.round_trips * 100) if self.round_trips else 0.0

    @property
    def profit_factor(self) -> float:
        return (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else float("inf")

    @property
    def net_pnl(self) -> float:
        return self.gross_profit - self.gross_loss


@dataclass
class Analytics:
    equity_start: float = 0.0
    equity_current: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    n_fills: int = 0
    n_round_trips: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    realized_pnl: float = 0.0
    per_strategy: dict[str, dict] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _round_trip_pnl(fills: list[dict]) -> tuple[list[tuple[str, float]], float]:
    """FIFO-match buys and sells per symbol into realized round-trip P&L.

    Returns (list of (strategy, pnl), total_realized). Sells are matched against the
    earliest open buy lots; the *sell's* strategy tag attributes the round trip
    (that's the decision that closed the trade).
    """
    from collections import deque

    lots: dict[str, deque] = defaultdict(deque)  # symbol -> deque of [qty, price]
    results: list[tuple[str, float]] = []
    total = 0.0
    # fills come newest-first from the store; process oldest-first.
    for f in sorted(fills, key=lambda r: (r["timestamp"], r["id"])):
        sym, side, qty, price = f["symbol"], f["side"], float(f["qty"]), float(f["price"])
        if side == "buy":
            lots[sym].append([qty, price])
        else:  # sell -> realize against open buy lots
            remaining = qty
            pnl = 0.0
            while remaining > 1e-9 and lots[sym]:
                lot = lots[sym][0]
                take = min(remaining, lot[0])
                pnl += take * (price - lot[1])
                lot[0] -= take
                remaining -= take
                if lot[0] <= 1e-9:
                    lots[sym].popleft()
            results.append((f.get("order_id", ""), pnl))
            total += pnl
    return results, total


def compute_analytics(store: Store) -> Analytics:
    a = Analytics()

    # --- equity-based metrics ---
    curve = store.get_equity_curve(limit=100_000)
    if curve:
        eqs = np.array([c["equity"] for c in curve], dtype=float)
        a.equity_start = float(eqs[0])
        a.equity_current = float(eqs[-1])
        if a.equity_start > 0:
            a.total_return_pct = (a.equity_current / a.equity_start - 1) * 100
        peak = np.maximum.accumulate(eqs)
        dd = (peak - eqs) / peak
        a.max_drawdown_pct = float(np.max(dd) * 100) if len(dd) else 0.0
        if len(eqs) > 2:
            rets = np.diff(eqs) / eqs[:-1]
            if np.std(rets) > 0:
                a.sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252))

    # --- trade-based metrics (realized round trips) ---
    fills = store.get_fills(limit=100_000)
    a.n_fills = len(fills)

    # Map order_id -> strategy for attribution.
    orders = {o["broker_order_id"] or o["client_order_id"]: o for o in store.get_orders(limit=100_000)}
    per: dict[str, TradeStat] = defaultdict(lambda: TradeStat(strategy="?"))

    rt_results, total_realized = _round_trip_pnl(fills)
    a.realized_pnl = round(total_realized, 2)
    a.n_round_trips = len(rt_results)
    for order_id, pnl in rt_results:
        strat = (orders.get(order_id, {}) or {}).get("strategy") or "unknown"
        st = per[strat]
        st.strategy = strat
        st.round_trips += 1
        if pnl >= 0:
            st.wins += 1
            st.gross_profit += pnl
        else:
            st.losses += 1
            st.gross_loss += -pnl

    total_wins = sum(s.wins for s in per.values())
    a.win_rate_pct = round(total_wins / a.n_round_trips * 100, 1) if a.n_round_trips else 0.0
    gp = sum(s.gross_profit for s in per.values())
    gl = sum(s.gross_loss for s in per.values())
    a.profit_factor = round(gp / gl, 2) if gl > 0 else (float("inf") if gp > 0 else 0.0)

    a.per_strategy = {
        name: {
            "round_trips": s.round_trips,
            "win_rate_pct": round(s.win_rate, 1),
            "net_pnl": round(s.net_pnl, 2),
            "profit_factor": (round(s.profit_factor, 2) if s.profit_factor != float("inf") else None),
        }
        for name, s in sorted(per.items())
    }

    a.summary = _plain_english(a)
    return a


def _plain_english(a: Analytics) -> str:
    if a.equity_start <= 0 and a.n_fills == 0:
        return "No activity yet — the bot hasn't traded."
    dir_word = "up" if a.total_return_pct >= 0 else "down"
    parts = [
        f"Portfolio is {dir_word} {abs(a.total_return_pct):.2f}% "
        f"(${a.equity_current:,.0f} from ${a.equity_start:,.0f}).",
    ]
    if a.n_round_trips:
        parts.append(
            f"{a.n_round_trips} completed trade(s), {a.win_rate_pct:.0f}% winners, "
            f"realized P&L ${a.realized_pnl:,.0f}."
        )
    else:
        parts.append(f"{a.n_fills} fill(s) so far; no round trips closed yet.")
    if a.max_drawdown_pct > 0:
        parts.append(f"Worst dip from a peak was {a.max_drawdown_pct:.1f}%.")
    if a.per_strategy:
        best = max(a.per_strategy.items(), key=lambda kv: kv[1]["net_pnl"], default=None)
        if best and best[1]["round_trips"]:
            parts.append(f"Best strategy so far: {best[0]} (net ${best[1]['net_pnl']:,.0f}).")
    return " ".join(parts)
