"""Notifier interface + severity levels."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntEnum


class Level(IntEnum):
    INFO = 10
    WARNING = 20
    CRITICAL = 30

    @classmethod
    def parse(cls, s: str) -> "Level":
        return {"info": cls.INFO, "warning": cls.WARNING, "critical": cls.CRITICAL}.get(
            (s or "").lower(), cls.INFO
        )


class Notifier(ABC):
    name: str = "notifier"

    @abstractmethod
    def send(self, title: str, message: str, level: Level) -> bool:
        """Best-effort send. Returns True on success, never raises."""
        ...
