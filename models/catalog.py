from __future__ import annotations

from typing import Iterable, Iterator

from game.categories import CATEGORY_KEYS
from models.character import Character


class CharacterCatalog:
    """In-memory, read-mostly view of the characters table (static game data)."""

    def __init__(self, characters: Iterable[Character] = ()) -> None:
        self.by_id: dict[str, Character] = {c.id: c for c in characters}
        self._pools: dict[str, list[Character]] = {k: [] for k in CATEGORY_KEYS}
        for c in self.by_id.values():
            for cat in c.categories:
                if cat in self._pools:
                    self._pools[cat].append(c)

    def get(self, char_id: str) -> Character:
        return self.by_id[char_id]

    def pool(self, category: str) -> list[Character]:
        return self._pools[category]

    def all(self) -> Iterator[Character]:
        return iter(self.by_id.values())

    def __len__(self) -> int:
        return len(self.by_id)
