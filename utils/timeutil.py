from __future__ import annotations

from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return utcnow().isoformat()


def in_minutes_iso(minutes: int) -> str:
    return (utcnow() + timedelta(minutes=minutes)).isoformat()
