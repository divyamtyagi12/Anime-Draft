"""Shared application context (settings, repositories, catalog, locks, tasks)."""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Coroutine, Hashable

from telegram import Bot

from config import Settings
from database.client import Database
from models.catalog import CharacterCatalog
from repositories.characters import CharacterRepo
from repositories.drafts import DraftRepo
from repositories.games import GameRepo
from repositories.groups import GroupRepo
from repositories.leaderboard import LeaderboardRepo
from repositories.matches import MatchRepo
from repositories.players import PlayerRepo
from repositories.standings import StandingsRepo
from repositories.users import UserRepo

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    users: UserRepo
    groups: GroupRepo
    games: GameRepo
    players: PlayerRepo
    drafts: DraftRepo
    matches: MatchRepo
    standings: StandingsRepo
    characters: CharacterRepo
    leaderboard: LeaderboardRepo
    catalog: CharacterCatalog = field(default_factory=CharacterCatalog)
    rng: random.Random = field(default_factory=random.SystemRandom)
    bot: Bot | None = None
    bot_username: str = ""
    running_games: set[int] = field(default_factory=set)
    _locks: dict[Hashable, asyncio.Lock] = field(default_factory=dict)
    _tasks: set[asyncio.Task] = field(default_factory=set)
    _teams: dict[int, dict] = field(default_factory=dict)

    @classmethod
    def create(cls, settings: Settings, db: Database) -> "AppContext":
        return cls(settings, db, UserRepo(db), GroupRepo(db), GameRepo(db), PlayerRepo(db),
                   DraftRepo(db), MatchRepo(db), StandingsRepo(db), CharacterRepo(db), LeaderboardRepo(db))

    def lock(self, key: Hashable) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def spawn(self, coro: Coroutine[Any, Any, Any], name: str | None = None) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            self._tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                log.error("Background task %s failed", name, exc_info=t.exception())

        task.add_done_callback(_done)
        return task

    async def load_team(self, gp_id: int) -> dict[str, Any]:
        """category -> Character (teams are immutable once locked, so cached)."""
        if gp_id not in self._teams:
            raw = await self.drafts.get_team(gp_id)
            if raw is None:
                raise RuntimeError(f"Team missing for game_player {gp_id}")
            self._teams[gp_id] = {cat: self.catalog.get(cid) for cat, cid in raw.items()}
        return self._teams[gp_id]
