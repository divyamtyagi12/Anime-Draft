"""Thin async wrapper around the (synchronous) supabase-py client.

Calls run in a worker thread so they never block the event loop; transient
network errors are retried with backoff. Credentials are never logged.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import httpx
from postgrest.exceptions import APIError
from supabase import Client, create_client

log = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Supabase/network failure after retries."""


def is_unique_violation(exc: BaseException) -> bool:
    return isinstance(exc, APIError) and str(getattr(exc, "code", "")) == "23505"


class Database:
    def __init__(self, url: str, key: str) -> None:
        self._client: Client = create_client(url, key)

    async def exec(self, build: Callable[[Client], Any], *, retries: int = 3) -> Any:
        """`build(client)` returns a postgrest request; we execute it and return `.data`."""

        def _run() -> Any:
            return build(self._client).execute().data

        delay = 0.5
        for attempt in range(1, retries + 1):
            try:
                return await asyncio.to_thread(_run)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt == retries:
                    raise DatabaseError(f"Supabase unreachable: {type(exc).__name__}") from exc
                log.warning("Supabase network error (%s), retry %d/%d", type(exc).__name__, attempt, retries)
                await asyncio.sleep(delay)
                delay *= 2

    async def rpc(self, fn: str, params: dict[str, Any]) -> Any:
        return await self.exec(lambda c: c.rpc(fn, params))
