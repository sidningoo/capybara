"""Strategy registry — the "playbook".

Central place that knows every available strategy. The selector picks a name from
here; the orchestrator and API list from here. Adding a strategy = add one line.
"""
from __future__ import annotations

from capybara.strategies.base import Strategy
from capybara.strategies.breakout import BreakoutStrategy
from capybara.strategies.mean_reversion import MeanReversionStrategy
from capybara.strategies.momentum import MomentumStrategy


def default_playbook() -> dict[str, Strategy]:
    """Instantiate the default set of strategies (Phase 1)."""
    strategies: list[Strategy] = [
        MomentumStrategy(),
        MeanReversionStrategy(),
        BreakoutStrategy(),
    ]
    return {s.name: s for s in strategies}


#: The special "no strategy / stay in cash" pseudo-selection.
CASH = "cash"
