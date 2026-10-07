"""Logging with secret redaction (tokens/keys never reach the log output)."""
from __future__ import annotations

import logging
import sys
from typing import Iterable


class RedactingFormatter(logging.Formatter):
    def __init__(self, secrets: Iterable[str], fmt: str) -> None:
        super().__init__(fmt)
        self._secrets = [s for s in secrets if s and len(s) >= 6]

    def format(self, record: logging.LogRecord) -> str:
        out = super().format(record)  # includes tracebacks
        for secret in self._secrets:
            out = out.replace(secret, "***REDACTED***")
        return out


def setup_logging(level: str, secrets: Iterable[str]) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingFormatter(secrets, "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level, logging.INFO))
    # httpx logs full request URLs, which contain the bot token.
    for noisy in ("httpx", "httpcore", "hpack", "postgrest", "hpack.hpack"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
