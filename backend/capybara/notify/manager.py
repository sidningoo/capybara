"""NotificationManager — routes engine events to configured channels.

Builds the active notifier set from config, filters by a minimum severity, and
de-duplicates bursts of the same event type so the user isn't spammed. Sending is
best-effort and never raises into the trading loop.
"""
from __future__ import annotations

from datetime import datetime, timezone

from capybara.config import Settings
from capybara.logging_setup import get_logger
from capybara.notify.base import Level, Notifier

log = get_logger("notify")


class NotificationManager:
    def __init__(self, settings: Settings):
        self.s = settings
        self.min_level = Level.parse(settings.notify_min_level)
        self.dedup_seconds = settings.notify_dedup_seconds
        self.notifiers: list[Notifier] = []
        self._last_sent: dict[str, datetime] = {}
        if settings.enable_notifications:
            self._build()

    def _build(self) -> None:
        if self.s.notify_webhook_url:
            from capybara.notify.webhook import WebhookNotifier
            self.notifiers.append(WebhookNotifier(self.s.notify_webhook_url))
        if self.s.smtp_host and self.s.notify_email_to:
            from capybara.notify.email import EmailNotifier
            self.notifiers.append(EmailNotifier(
                host=self.s.smtp_host, port=self.s.smtp_port,
                username=self.s.smtp_user, password=self.s.smtp_password,
                sender=self.s.smtp_from, recipient=self.s.notify_email_to,
            ))
        if self.notifiers:
            log.info("Notifications enabled via: %s", ", ".join(n.name for n in self.notifiers))

    @property
    def enabled(self) -> bool:
        return bool(self.notifiers)

    def notify(self, event_type: str, title: str, message: str, level: Level = Level.INFO,
               dedup: bool = True) -> None:
        if not self.notifiers or level < self.min_level:
            return
        now = datetime.now(timezone.utc)
        if dedup:
            last = self._last_sent.get(event_type)
            if last and (now - last).total_seconds() < self.dedup_seconds:
                return
        self._last_sent[event_type] = now
        for n in self.notifiers:
            try:
                n.send(title, message, level)
            except Exception as exc:  # pragma: no cover
                log.warning("notifier %s failed: %s", n.name, exc)

    def send_digest(self, text: str, tag: str = "daily_digest") -> None:
        """Send the daily digest regardless of min_level (deduped by tag+date)."""
        if not self.notifiers:
            return
        key = f"{tag}:{datetime.now(timezone.utc).date().isoformat()}"
        if self._last_sent.get(key):
            return
        self._last_sent[key] = datetime.now(timezone.utc)
        for n in self.notifiers:
            try:
                n.send("Daily digest", text, Level.INFO)
            except Exception as exc:  # pragma: no cover
                log.warning("digest via %s failed: %s", n.name, exc)
