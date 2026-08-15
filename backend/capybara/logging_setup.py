"""Structured logging setup. JSON-ish lines that are easy to grep and ship."""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [handler]
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
