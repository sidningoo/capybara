"""Plain-English daily digest.

Turns the day's activity into a short, readable summary a hands-off user can skim on
their phone: what the bot did, where it stands, and anything that needs attention.
This is the "just push me a summary" experience.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from capybara.analytics.performance import compute_analytics
from capybara.store.db import Store


def build_digest(store: Store, snapshot: dict | None = None) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    lines: list[str] = [f"🐹 Capybara daily digest — {today}"]

    # --- Portfolio standing ---
    if snapshot and snapshot.get("account"):
        acct = snapshot["account"]
        gr = snapshot.get("guardrails", {}) or {}
        eq = acct["equity"]
        day_start = gr.get("day_start_equity")
        line = f"Equity: ${eq:,.0f}"
        if day_start:
            day_pnl = eq - day_start
            pct = (day_pnl / day_start * 100) if day_start else 0.0
            line += f" ({'+' if day_pnl >= 0 else ''}${day_pnl:,.0f}, {pct:+.2f}% today)"
        lines.append(line)
        state = snapshot.get("state", "?")
        lines.append(f"Engine: {state} · autonomy L{snapshot.get('autonomy_level', '?')}")
        if snapshot.get("halt_reason"):
            lines.append(f"⚠ HALTED: {snapshot['halt_reason']}")

    # --- What it did today (fills) ---
    fills = [f for f in store.get_fills(limit=1000) if str(f["timestamp"]).startswith(today)]
    if fills:
        buys = [f for f in fills if f["side"] == "buy"]
        sells = [f for f in fills if f["side"] == "sell"]
        traded = Counter(f["symbol"] for f in fills)
        top = ", ".join(f"{sym}×{n}" for sym, n in traded.most_common(5))
        lines.append(f"Trades today: {len(buys)} buy(s), {len(sells)} sell(s). Symbols: {top}.")
    else:
        lines.append("No trades today.")

    # --- Current stance ---
    if snapshot:
        positions = snapshot.get("positions", [])
        if positions:
            pos_str = ", ".join(
                f"{p['symbol']} ({p['unrealized_pl_pct']:+.1f}%)" for p in positions[:6]
            )
            lines.append(f"Open positions: {pos_str}.")
        else:
            lines.append("No open positions (in cash).")
        sels = snapshot.get("selections", {})
        active = {s: v for s, v in sels.items() if v.get("strategy") not in (None, "cash")}
        if active:
            stance = ", ".join(f"{s}:{v['strategy']}" for s, v in list(active.items())[:6])
            lines.append(f"Current stance: {stance}.")

    # --- Performance summary ---
    analytics = compute_analytics(store)
    lines.append("Performance: " + analytics.summary)

    # --- Anything needing attention ---
    pending = store.get_orders(limit=100, status="pending_approval")
    if pending:
        lines.append(f"⏳ {len(pending)} order(s) awaiting your approval.")

    return "\n".join(lines)
