"""Shared builder for IPL integration tests: real Postgres + fake Telegram, scripted human managers."""
from __future__ import annotations

import asyncio
import random
from types import SimpleNamespace

from ipl_draft.config import IplSettings
from ipl_draft.data.seed_loader import build_seed_payload
from ipl_draft.handlers import callbacks
from ipl_draft.runtime import IplRuntime
from ipl_draft.services import simulation_worker
from tests.support import fakes, pgdb

RESET = """
truncate ipl_tournaments restart identity cascade;
truncate ipl_user_stats, ipl_group_stats;
"""
GROUP = 5000


def fast_settings(**kw) -> IplSettings:
    base = dict(draft_seconds=30, matchday_delay=0, playoff_delay=0, system_announce_delay=0, tick_seconds=0.05,
                store_ball_events=True, summary_every=5)
    base.update(kw)
    return IplSettings(**base)


class Harness:
    def __init__(self, **settings) -> None:
        self.db = pgdb.PgDatabase()
        self.ctx = fakes.FakeCtx(self.db)
        self.rt = IplRuntime.create(self.ctx, fast_settings(**settings))
        self.rt.sleep = _nosleep
        self.context = SimpleNamespace(bot_data={"ipl": self.rt, "ctx": self.ctx}, bot=self.ctx.bot)
        self.chat = fakes.FakeChat(GROUP)
        self.ctx.bot.admins.add(1)

    # ── setup ──
    @staticmethod
    def reset_db() -> None:
        pgdb.run_sql(RESET)

    async def ensure_players(self) -> None:
        pool = await self.rt.repo.pool_summary()
        if pool["eligible"] >= 300:
            return
        src, rows = build_seed_payload()
        for i in range(0, len(rows), 40):
            await self.rt.repo.import_players(src, rows[i:i + 40])

    async def click(self, data: str, uid: int, *, chat=None, message_id: int = 1):
        q = fakes.FakeQuery(data, fakes.FakeUser(uid), chat or self.chat, message_id)
        q.message.chat = chat or self.chat
        update = SimpleNamespace(callback_query=q)
        await callbacks.ipl_callback(update, self.context)
        return q

    async def lobby(self, humans: list[int], group: int = GROUP, join: bool = True) -> int:
        """Host = first human. Returns the tournament id."""
        from ipl_draft.services import tournament_service
        for u in humans:
            await self.ctx.users.upsert(u, None, f"Manager{u}", dm_started=True)
        await self.ctx.groups.upsert(group, "Test Group")
        t = await tournament_service.create_lobby(self.rt, group, humans[0])
        assert t, "lobby not created"
        if join:
            for u in humans:
                q = await self.click(f"ipl:j:{t['id']}", u, chat=fakes.FakeChat(group))
                assert q.answers[-1][0] and "joined" in q.answers[-1][0], q.answers
        return t["id"]

    async def force_start(self, tid: int, uid: int = 1, group: int = GROUP):
        return await self.click(f"ipl:st:{tid}", uid, chat=fakes.FakeChat(group))

    # ── scripted human drafting ──
    def open_offer_for(self, uid: int):
        """The newest DM to this user that carries pick buttons."""
        for m in reversed(self.ctx.bot.sent):
            if m.chat_id == uid and m.markup and any(b.callback_data and b.callback_data.startswith("ipl:pk:")
                                                     for r in m.markup.inline_keyboard for b in r):
                return m
        return None

    async def human_picks(self, uid: int, rng: random.Random, choose=None) -> bool:
        m = self.open_offer_for(uid)
        if not m:
            return False
        btns = [b for r in m.markup.inline_keyboard for b in r if b.callback_data.startswith("ipl:pk:")]
        b = choose(btns) if choose else rng.choice(btns)
        q = await self.click(b.callback_data, uid, chat=fakes.FakeChat(uid, "private"), message_id=m.message_id)
        if q.answers and q.answers[-1][1]:
            return False
        offer, pos = b.callback_data.split(":")[2:4]
        q = await self.click(f"ipl:cf:{offer}:{pos}", uid, chat=fakes.FakeChat(uid, "private"), message_id=m.message_id)
        return bool(q.answers) and q.answers[-1][0] == "✅ Player drafted!"

    async def draft_all(self, humans: list[int], seed: int = 3) -> None:
        rng = random.Random(seed)
        for _ in range(11 * len(humans) * 3):
            progressed = False
            for u in humans:
                progressed |= await self.human_picks(u, rng)
            await asyncio.sleep(0)
            if not progressed:
                row = pgdb.run_sql("select count(*) from ipl_tournaments where state = 'DRAFTING'")
                if row == "0":
                    break
                await asyncio.sleep(0.05)

    async def run_to_end(self, tid: int, timeout: float = 600) -> dict:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await self.ctx.drain()
            t = await self.rt.repo.get(tid)
            if t["state"] in ("COMPLETED", "CANCELLED", "FAILED_RECOVERABLE"):
                return t
            await simulation_worker.tick(self.rt)
        raise TimeoutError("tournament did not finish")


async def _nosleep(_s: float) -> None:
    await asyncio.sleep(0)
