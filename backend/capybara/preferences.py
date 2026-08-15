"""Runtime preferences — the light-touch "recommendations" the user can give.

The whole point of Capybara is that you don't do research or micromanage. But you
should be able to *nudge* it: pick a risk appetite and choose what it's allowed to
trade. That's what this is — a small, persisted set of preferences (risk profile +
watchlist) that override the static env config at runtime, editable from the dashboard
without redeploying.

Persisted in the store's key-value table so they survive restarts.
"""
from __future__ import annotations

from capybara.config import RISK_PRESETS, Settings
from capybara.logging_setup import get_logger
from capybara.store.db import Store

log = get_logger("preferences")

_KEY = "preferences"


class PreferencesManager:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.s = settings
        saved = store.get_kv(_KEY, default=None) or {}
        self.risk_profile: str = saved.get("risk_profile", "balanced")
        self.watchlist: list[str] = saved.get("watchlist") or list(settings.universe_list)
        if self.risk_profile not in RISK_PRESETS:
            self.risk_profile = "balanced"

    # ───────────── persistence ─────────────
    def _persist(self) -> None:
        self.store.set_kv(_KEY, {"risk_profile": self.risk_profile, "watchlist": self.watchlist})

    # ───────────── mutations ─────────────
    def set_risk_profile(self, profile: str) -> bool:
        if profile not in RISK_PRESETS:
            return False
        self.risk_profile = profile
        self._persist()
        self.apply_risk_to_settings()
        self.store.log_event("set_risk_profile", {"profile": profile})
        return True

    def set_watchlist(self, symbols: list[str]) -> list[str]:
        cleaned = sorted({s.strip().upper() for s in symbols if s and s.strip()})
        self.watchlist = cleaned
        self._persist()
        self.store.log_event("set_watchlist", {"watchlist": cleaned})
        return self.watchlist

    def add_symbol(self, symbol: str) -> list[str]:
        return self.set_watchlist(self.watchlist + [symbol])

    def remove_symbol(self, symbol: str) -> list[str]:
        return self.set_watchlist([s for s in self.watchlist if s != symbol.strip().upper()])

    # ───────────── apply ─────────────
    def apply_risk_to_settings(self) -> None:
        """Push the selected preset's values onto the live Settings object so the
        risk manager and guardrails pick them up on the next cycle."""
        preset = RISK_PRESETS.get(self.risk_profile, {})
        for field, value in preset.items():
            setattr(self.s, field, value)
        log.info("Applied risk profile '%s'.", self.risk_profile)

    def snapshot(self) -> dict:
        preset = RISK_PRESETS.get(self.risk_profile, {})
        return {
            "risk_profile": self.risk_profile,
            "available_profiles": list(RISK_PRESETS.keys()),
            "watchlist": self.watchlist,
            "effective_risk": preset,
        }
