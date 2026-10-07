from data.characters import CHARACTERS
from game.categories import CATEGORY_KEYS
from models.catalog import CharacterCatalog
from models.character import Character


def build_catalog() -> CharacterCatalog:
    chars = []
    for c in CHARACTERS:
        row = {**c}
        chars.append(Character.from_row(row, c["categories"]))
    return CharacterCatalog(chars)
