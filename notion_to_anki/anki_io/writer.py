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
import threading
import time

_MAP_FILENAME = "notion_block_id_map.json"
_MEDIA_MAP_FILENAME = "notion_media_map.json"
_REPLACE_RETRIES = 10


def _user_files_path(filename: str) -> str:
    """Resolve a path inside user_files/, the only dir Anki keeps across updates."""
    # user_files/ lives alongside the notion_to_anki package directory
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    user_files = os.path.join(pkg_dir, "user_files")
    os.makedirs(user_files, exist_ok=True)
    return os.path.join(user_files, filename)


def _map_path() -> str:
    """Resolve the path to the persistent id-map file in user_files/."""
    return _user_files_path(_MAP_FILENAME)


def _media_map_path() -> str:
    """Resolve the path to the image-block → media-filename cache."""
    return _user_files_path(_MEDIA_MAP_FILENAME)


def load_media_map() -> dict[str, str]:
    """Load the image-block-id → media-filename cache.

    Media filenames are content hashes, so the only way to learn a file's name
    is to download it. Without this cache every sync re-downloaded every image
    (27 MB and most of a 17-minute run on the eMRCS page), and auto-sync would
    do it on every tick. Image block ids are stable, so they make a usable key.
    """
    path = _media_map_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_media_map(mapping: dict[str, str]) -> None:
    """Persist the image-block-id → media-filename cache atomically."""
    _atomic_write_json(_media_map_path(), mapping)


def load_id_map() -> dict[str, str]:
    """Load the persisted notion_block_id → note id map from user_files/.

    A damaged file returns an empty map rather than raising: re-adding cards is
    recoverable, but an uncaught decode error here would fail every future sync
    until the user deleted the file by hand.
    """
    path = _map_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_id_map(mapping: dict[str, str]) -> None:
    """Persist the notion_block_id → note id map to user_files/."""
    _atomic_write_json(_map_path(), mapping)


def _atomic_write_json(path: str, mapping: dict) -> None:
    """Write JSON to path atomically.

    Written to a temp file then renamed: os.replace is atomic, so a crash or a
    concurrent reader can never observe a half-written file. The temp name is
    per-writer — on Windows a shared one makes os.replace fail with a sharing
    violation if a second writer still has it open.
    """
    tmp = f"{path}.{os.getpid()}-{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(mapping, fh, indent=2)
        # Windows refuses to replace a file another handle currently has open.
        # Concurrent readers hold it for microseconds, so a short retry clears it.
        for attempt in range(_REPLACE_RETRIES):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def index_existing_notes(col) -> dict[str, str]:
    """Map NotionBlockId → note id by scanning the collection.

    The collection is the source of truth; the file in user_files/ is only a
    cache. Every synced note stores its own NotionBlockId, so a lost, stale or
    damaged cache can be rebuilt from it. Without this, a missing cache makes
    the next sync re-add every card as a duplicate instead of updating it.
    """
    found: dict[str, str] = {}
    try:
        note_ids = col.find_notes("NotionBlockId:_*")
    except Exception:
        return found

    for note_id in note_ids:
        try:
            block_id = col.get_note(note_id)["NotionBlockId"].strip()
        except Exception:
            continue
        if block_id:
            found[block_id] = str(note_id)
    return found


def upsert_card(col, card, deck_id: int, model, id_map: dict) -> str:
    """Add or update the note for card in deck_id. Returns the note id as a string.

    id_map is read and updated in place; the caller owns loading and persisting
    it. Doing that here meant a full re-read and re-write of the JSON per card.
    """
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
    return str(note.id)


def upsert_cloze_card(col, card, deck_id: int, model, id_map: dict) -> str:
    """Add or update a cloze note. Returns the note id as a string."""
    block_id = card.notion_block_id

    if block_id in id_map:
        note_id = int(id_map[block_id])
        try:
            note = col.get_note(note_id)
            _fill_cloze_note(note, card, model)
            col.update_note(note)
            return str(note_id)
        except Exception:
            pass

    note = col.new_note(model)
    _fill_cloze_note(note, card, model)
    col.add_note(note, deck_id)

    id_map[block_id] = str(note.id)
    return str(note.id)


def _fill_cloze_note(note, card, model) -> None:
    field_names = [f["name"] for f in model["flds"]]

    def _set(name: str, value: str) -> None:
        if name in field_names:
            note[name] = value

    _set("Text", card.text)
    _set("Back Extra", card.back_extra)
    _set("NotionBlockId", card.notion_block_id)


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
