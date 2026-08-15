"""Webhook notifier — Slack, Discord, or a generic JSON endpoint.

Auto-detects the payload format from the URL so the same config field works for
the common cases (Slack incoming webhooks, Discord webhooks) and anything else.
"""
from __future__ import annotations

import httpx

from capybara.logging_setup import get_logger
from capybara.notify.base import Level, Notifier

log = get_logger("notify.webhook")

_EMOJI = {Level.INFO: "🟢", Level.WARNING: "🟡", Level.CRITICAL: "🔴"}


class WebhookNotifier(Notifier):
    name = "webhook"

    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url
        self.timeout = timeout
        if "hooks.slack.com" in url:
            self.kind = "slack"
        elif "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
            self.kind = "discord"
        else:
            self.kind = "generic"

    def _payload(self, title: str, message: str, level: Level) -> dict:
        text = f"{_EMOJI.get(level, '')} *Capybara — {title}*\n{message}"
        if self.kind == "slack":
            return {"text": text}
        if self.kind == "discord":
            return {"content": f"{_EMOJI.get(level, '')} **Capybara — {title}**\n{message}"}
        return {"title": title, "message": message, "level": level.name.lower(), "source": "capybara"}

    def send(self, title: str, message: str, level: Level) -> bool:
        try:
            resp = httpx.post(self.url, json=self._payload(title, message, level), timeout=self.timeout)
            ok = resp.status_code < 300
            if not ok:
                log.warning("webhook %s returned %s", self.kind, resp.status_code)
            return ok
        except Exception as exc:  # pragma: no cover
            log.warning("webhook send failed: %s", exc)
            return False
