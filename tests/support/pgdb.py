"""`rpc()` adapter over plain PostgreSQL (psql subprocess) so the real IplRepo/services run against a real database.

Each call opens its own connection → concurrent awaits are genuinely concurrent transactions (used by the race tests).
Configure with IPL_TEST_PG, e.g.  "-h /var/tmp/ipl_pg -p 54329 -U postgres -d ipltest"  (tests skip when unset/unreachable).
Statements travel via stdin (no argv size limit).
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from typing import Any

DEFAULT = "-h /var/tmp/ipl_pg -p 54329 -U postgres -d ipltest"


class PgError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def conn_args() -> list[str]:
    return shlex.split(os.environ.get("IPL_TEST_PG", DEFAULT))


def run_sql(sql: str, *, timeout: float = 120) -> str:
    p = subprocess.run(["psql", *conn_args(), "-qAtX", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose", "-f", "-"],
                       input=sql, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        import re
        m = re.search(r"ERROR:\s+(\w{5}):\s*(.*)", p.stderr)
        raise PgError(m.group(1) if m else "XX000", (m.group(2) if m else p.stderr)[:400])
    return p.stdout.strip()


def available() -> bool:
    try:
        return run_sql("select 1 from ipl_tournaments limit 0; select 1", timeout=10) == "1"
    except Exception:  # noqa: BLE001
        return False


def _q(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def literal(v: Any, typ: str) -> str:
    if v is None:
        return "null"
    if typ in ("jsonb", "json"):
        return f"{_q(json.dumps(v))}::jsonb"
    if typ.endswith("[]"):
        base = typ[:-2]
        return "array[" + ",".join(literal(x, base) for x in v) + f"]::{typ}" if v else f"'{{}}'::{typ}"
    if typ == "boolean":
        return "true" if v else "false"
    if typ in ("bigint", "integer", "smallint", "numeric", "double precision"):
        return f"{v}::{typ}"
    return f"{_q(str(v))}::{typ}"


class PgDatabase:
    """Quacks like database.client.Database for the `.rpc` surface IplRepo uses."""

    def __init__(self) -> None:
        self._sig: dict[str, tuple[list[str], list[str], str]] = {}
        self.calls = 0

    def _signature(self, fn: str):
        if fn not in self._sig:
            out = run_sql(f"""select coalesce(array_to_string(proargnames, ','), ''), array_to_string(proargtypes::regtype[], ','),
                              prorettype::regtype from pg_proc where proname = {_q(fn)} and pronamespace = 'public'::regnamespace""")
            if not out:
                raise PgError("42883", f"function {fn} does not exist")
            names, types, ret = out.split("|")
            self._sig[fn] = (names.split(","), types.split(","), ret)
        return self._sig[fn]

    async def rpc(self, fn: str, params: dict[str, Any]) -> Any:
        names, types, ret = self._signature(fn)
        tmap = dict(zip(names, types))
        args = ", ".join(f"{k} => {literal(v, tmap[k])}" for k, v in params.items())
        call = f"public.{fn}({args})"
        sql = f"select {call};" if ret == "void" else f"select coalesce(to_jsonb({call}), 'null'::jsonb);"
        self.calls += 1
        out = await asyncio.to_thread(run_sql, sql)
        if ret == "void" or out == "":
            return None
        return json.loads(out)

    async def exec(self, build) -> Any:                       # pragma: no cover - table access isn't used by IPL
        raise NotImplementedError("PgDatabase only supports rpc()")
