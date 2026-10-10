"""Load check: N groups x M humans drafting + simulating concurrently against a test PostgreSQL (fake Telegram).

    IPL_TEST_PG="-h /var/tmp/ipl_pg -p 54329 -U postgres -d ipltest" python -m scripts.ipl_load_test --groups 4 --humans 3
Reports wall time, DB calls and verifies no player is shared inside a tournament. NOT a Supabase/Telegram benchmark.
"""
import argparse
import asyncio
import time

from tests.support import stubs

stubs.install()
from tests.support import fakes, pgdb  # noqa: E402
from tests.support.harness import Harness  # noqa: E402


async def main(groups: int, humans: int) -> None:
    h = Harness()
    Harness.reset_db()
    await h.ensure_players()
    tids, users, uid = [], [], 1
    for g in range(groups):
        us = list(range(uid, uid + humans))
        uid += humans
        h.ctx.bot.admins.add(us[0])
        tid = await h.lobby(us, group=9000 + g)
        await h.force_start(tid, us[0], 9000 + g)
        tids.append(tid)
        users += us
    t0 = time.time()
    await h.ctx.drain()
    await h.draft_all(users)
    t1 = time.time()
    for tid in tids:
        await h.run_to_end(tid)
    t2 = time.time()
    bad = pgdb.run_sql("select count(*) from (select tournament_id, player_id from ipl_team_rosters group by 1,2 having count(*)>1) x")
    print(f"groups={groups} humans={humans} draft={t1 - t0:.1f}s sim={t2 - t1:.1f}s db_calls={h.db.calls} duplicate_players={bad}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", type=int, default=3)
    ap.add_argument("--humans", type=int, default=3)
    a = ap.parse_args()
    asyncio.run(main(a.groups, a.humans))
