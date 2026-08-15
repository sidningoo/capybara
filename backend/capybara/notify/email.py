"""Email notifier via SMTP (stdlib, no extra deps)."""
from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

from capybara.logging_setup import get_logger
from capybara.notify.base import Level, Notifier

log = get_logger("notify.email")


class EmailNotifier(Notifier):
    name = "email"

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipient: str,
        use_tls: bool = True,
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender or username
        self.recipient = recipient
        self.use_tls = use_tls
        self.timeout = timeout

    def send(self, title: str, message: str, level: Level) -> bool:
        try:
            msg = MIMEText(message)
            msg["Subject"] = f"[Capybara/{level.name}] {title}"
            msg["From"] = self.sender
            msg["To"] = self.recipient
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as server:
                if self.use_tls:
                    server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(self.sender, [self.recipient], msg.as_string())
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("email send failed: %s", exc)
            return False
