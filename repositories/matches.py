from __future__ import annotations

from database.client import Database
from game.battle import MatchResult
from game.tournament import round_robin
from utils.timeutil import now_iso


class MatchRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def ensure_fixtures(self, game_id: int, gp_ids: list[int]) -> bool:
        """Create the round-robin schedule once. True if newly created."""
        existing = await self.db.exec(
            lambda c: c.table("matches").select("id").eq("game_id", game_id).eq("stage", "LEAGUE").limit(1))
        if existing:
            return False
        rows = [
            {"game_id": game_id, "stage": "LEAGUE", "round_no": rn, "p1_id": a, "p2_id": b}
            for rn, pairs in enumerate(round_robin(sorted(gp_ids)), start=1)
            for a, b in pairs
        ]
        if rows:
            await self.db.exec(lambda c: c.table("matches").upsert(
                rows, on_conflict="game_id,stage,p1_id,p2_id", ignore_duplicates=True))
        return True

    async def list_for_game(self, game_id: int, stage: str | None = None) -> list[dict]:
        def build(c):
            q = c.table("matches").select("*").eq("game_id", game_id)
            if stage:
                q = q.eq("stage", stage)
            return q.order("round_no").order("id")
        return await self.db.exec(build)

    async def get(self, match_id: int) -> dict | None:
        rows = await self.db.exec(lambda c: c.table("matches").select("*").eq("id", match_id).limit(1))
        return rows[0] if rows else None

    async def final_for_game(self, game_id: int) -> dict | None:
        rows = await self.db.exec(
            lambda c: c.table("matches").select("*").eq("game_id", game_id).eq("stage", "FINAL").limit(1))
        return rows[0] if rows else None

    async def claim(self, match_id: int) -> bool:
        """PENDING -> RUNNING; exactly one caller gets True (no double execution)."""
        rows = await self.db.exec(
            lambda c: c.table("matches").update({"status": "RUNNING", "started_at": now_iso()})
            .eq("id", match_id).eq("status", "PENDING"))
        return bool(rows)

    async def finish(self, match_id: int, result: MatchResult) -> bool:
        clashes = [
            {"clash_no": c.clash_no, "category": c.category,
             "p1_character_id": c.p1_char.id, "p2_character_id": c.p2_char.id,
             "p1_rating": c.p1_rating, "p2_rating": c.p2_rating,
             "p1_score": c.p1_score, "p2_score": c.p2_score, "winner_side": c.winner_side}
            for c in result.clashes
        ]
        tb = result.tiebreak
        return bool(await self.db.rpc("finish_match", {
            "p_match_id": match_id, "p_clashes": clashes, "p_winner_side": result.winner_side,
            "p_tb1": tb.p1_score if tb else None, "p_tb2": tb.p2_score if tb else None}))

    async def clashes(self, match_id: int) -> list[dict]:
        return await self.db.exec(
            lambda c: c.table("match_clashes").select("*").eq("match_id", match_id).order("clash_no"))

    async def mark_notified(self, match_id: int) -> None:
        await self.db.exec(lambda c: c.table("matches").update({"notified": True}).eq("id", match_id))

    async def reset_running(self, game_id: int | None = None) -> None:
        """Orphaned RUNNING matches (crash/restart) go back to PENDING."""
        def build(c):
            q = c.table("matches").update({"status": "PENDING"}).eq("status", "RUNNING")
            return q.eq("game_id", game_id) if game_id is not None else q
        await self.db.exec(build)
