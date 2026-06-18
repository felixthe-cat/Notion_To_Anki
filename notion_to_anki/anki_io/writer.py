"""Idempotent note writing.

Maintains a persistent map notion_block_id -> note id (stored in user_files/ so
it survives add-on updates). On each sync:
  * unseen block id  → add a new note in the target deck
  * known block id   → update the existing note's fields if the source changed
  * never auto-delete; honour the on_source_deleted config (ignore / suspend / tag)
"""
from __future__ import annotations

import json
import os

_MAP_FILENAME = "notion_block_id_map.json"


def _map_path() -> str:
    """Resolve the path to the persistent id-map file in user_files/."""
    # user_files/ lives alongside the notion_to_anki package directory
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    user_files = os.path.join(pkg_dir, "user_files")
    os.makedirs(user_files, exist_ok=True)
    return os.path.join(user_files, _MAP_FILENAME)


def load_id_map() -> dict[str, str]:
    """Load the persisted notion_block_id → note id map from user_files/."""
    path = _map_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_id_map(mapping: dict[str, str]) -> None:
    """Persist the notion_block_id → note id map to user_files/."""
    with open(_map_path(), "w", encoding="utf-8") as fh:
        json.dump(mapping, fh, indent=2)


def upsert_card(col, card, deck_id: int, model) -> str:
    """Add or update the note for card in deck_id. Returns the note id as a string."""
    id_map = load_id_map()
    block_id = card.notion_block_id

    if block_id in id_map:
        note_id = int(id_map[block_id])
        try:
            note = col.get_note(note_id)
            _fill_note(note, card, model)
            col.update_note(note)
            return str(note_id)
        except Exception:
            # Note was deleted manually; fall through to re-add it
            pass

    note = col.new_note(model)
    _fill_note(note, card, model)
    col.add_note(note, deck_id)

    id_map[block_id] = str(note.id)
    save_id_map(id_map)
    return str(note.id)


def _fill_note(note, card, model) -> None:
    """Populate note fields from a Card, tolerating missing fields gracefully."""
    field_names = [f["name"] for f in model["flds"]]

    def _set(name: str, value: str) -> None:
        if name in field_names:
            note[name] = value

    _set("Front", card.front)
    _set("Back", card.back)
    _set("Extra", card.extra)
    _set("NotionBlockId", card.notion_block_id)
