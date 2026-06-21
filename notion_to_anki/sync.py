"""Sync orchestration — ties the Notion client, converters, and Anki writer together.

A full sync works on any mix of Notion page IDs and database IDs:

  Page IDs:
    1. Fetch title → deck name.
    2. Fetch full block tree (recursive).
    3. Top-level toggle blocks → Basic cards.
    4. Top-level paragraph/heading blocks with {{cN::...}} → Cloze cards.
    5. Top-level table blocks → one Basic card per data row.
    6. Audio blocks inside toggle children → [sound:filename] in Back/Extra.
    7. child_page / child_database blocks → recurse as subdecks.

  Database IDs (auto-detected):
    1. Fetch database title → deck name.
    2. Query all pages in the database.
    3. For each page: fetch block tree → extract cards → create in a subdeck
       named after the page's title property.

Designed to run off the main thread via aqt QueryOp.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class SyncCancelledError(Exception):
    """Raised when the user requests cancellation mid-sync."""
    def __init__(self, partial_result: "SyncResult") -> None:
        super().__init__("Sync stopped by user")
        self.partial_result = partial_result


@dataclass
class SyncResult:
    """Summary of a completed sync run."""
    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    decks_touched: list[str] = field(default_factory=list)
    per_page_results: dict = field(default_factory=dict)  # page_id → result dict


def run_sync(
    page_ids: list[str] | None = None,
    col=None,
    config: dict | None = None,
    progress_cb=None,
    cancel_event=None,
) -> SyncResult:
    """Run a full sync. Returns a SyncResult summary.

    progress_cb: optional callable(str) -> None, called from the background
    thread to report status messages. Implementations must be thread-safe.
    """
    if col is None:
        try:
            from aqt import mw  # type: ignore
            col = mw.col
        except ImportError:
            raise RuntimeError("No collection provided and aqt is not available")

    if config is None:
        try:
            import os
            from aqt import mw  # type: ignore
            _name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
            config = mw.addonManager.getConfig(_name) or {}
        except ImportError:
            config = {}

    token: str = config.get("notion_token", "")
    if not token:
        raise ValueError("Notion token is not configured. Open Tools → NotionSync for Anki.")

    if page_ids is None:
        page_ids = config.get("page_ids", [])

    deck_root: str = config.get("deck_root", "")

    from .notion.client import NotionClient
    from .notion.blocks import fetch_block_tree, get_page_title, get_database_title
    from .convert.toggles import (
        collect_top_level_toggles, toggle_to_card,
        collect_cloze_blocks, block_to_cloze_card,
        table_to_cards,
    )
    from .convert.media import image_block_url, ingest_image, audio_block_url, ingest_audio
    from .anki_io.models import ensure_model, ensure_cloze_model
    from .anki_io.decks import ensure_deck, deck_name_for
    from .anki_io.writer import upsert_card, upsert_cloze_card, load_id_map, save_id_map

    def _report(msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    _report("Initialising...")
    client = NotionClient(token)
    model = ensure_model(col)
    cloze_model = ensure_cloze_model(col)
    result = SyncResult()
    id_map = load_id_map()

    # Mutable progress counters shared across closures
    _pg = {"num": 0, "card_n": 0, "card_total": 0}

    def _pg_prefix() -> str:
        total_pages = len(page_ids or [])
        return f"Page {_pg['num']} of {total_pages}  ·  " if total_pages > 1 else ""

    def _register_deck(name: str) -> int:
        did = ensure_deck(col, name)
        if name not in result.decks_touched:
            result.decks_touched.append(name)
        return did

    def _add_cards_from_blocks(blocks: list[dict], deck_id: int, deck_name: str) -> None:
        """Convert all card-bearing blocks to notes, then recurse into sub-pages/dbs."""

        toggles = collect_top_level_toggles(blocks)
        clozes  = collect_cloze_blocks(blocks)
        tables  = [b for b in blocks if b.get("type") == "table"]
        total   = len(toggles) + len(clozes) + sum(
            len(t.get("children", [])) for t in tables
        )

        _pg["card_n"] = 0
        _pg["card_total"] = total

        if total:
            _report(_pg_prefix() + f"'{deck_name}'  —  {total} card{'s' if total != 1 else ''}")
        else:
            _report(_pg_prefix() + f"'{deck_name}'  —  scanning...")

        def _card_progress():
            if cancel_event and cancel_event.is_set():
                raise SyncCancelledError(result)
            _pg["card_n"] += 1
            _report(
                _pg_prefix()
                + f"Card {_pg['card_n']} of {_pg['card_total']}  —  {deck_name}"
            )

        # 1. Toggle → Basic cards
        for toggle_block in toggles:
            _card_progress()
            try:
                card = toggle_to_card(toggle_block)
                if not card.front.strip():
                    result.skipped += 1
                    continue
                card = _process_media(card, toggle_block, col,
                                      ingest_image, image_block_url,
                                      ingest_audio, audio_block_url)
                block_id = card.notion_block_id
                was_known = block_id in id_map
                note_id = upsert_card(col, card, deck_id, model)
                id_map[block_id] = note_id
                if was_known:
                    result.updated += 1
                else:
                    result.added += 1
            except Exception as exc:
                result.errors.append(f"Block {toggle_block.get('id', '?')}: {exc}")

        # 2. Paragraph/heading with {{cN::...}} → Cloze cards
        for cloze_block in clozes:
            _card_progress()
            try:
                card = block_to_cloze_card(cloze_block)
                block_id = card.notion_block_id
                was_known = block_id in id_map
                note_id = upsert_cloze_card(col, card, deck_id, cloze_model)
                id_map[block_id] = note_id
                if was_known:
                    result.updated += 1
                else:
                    result.added += 1
            except Exception as exc:
                result.errors.append(f"Cloze {cloze_block.get('id', '?')}: {exc}")

        # 3. Table → one Basic card per row
        for block in tables:
            for card in table_to_cards(block):
                _card_progress()
                try:
                    block_id = card.notion_block_id
                    was_known = block_id in id_map
                    note_id = upsert_card(col, card, deck_id, model)
                    id_map[block_id] = note_id
                    if was_known:
                        result.updated += 1
                    else:
                        result.added += 1
                except Exception as exc:
                    result.errors.append(f"Table row {card.notion_block_id}: {exc}")

        # 4. Recurse into child pages / databases
        for block in blocks:
            if cancel_event and cancel_event.is_set():
                raise SyncCancelledError(result)
            btype = block.get("type")
            child_id = block.get("id", "")
            if not child_id:
                continue
            if btype in ("child_page", "child_database"):
                _sync_any(child_id, parent_deck_name=deck_name)

    def _sync_any(notion_id: str, parent_deck_name: str | None = None) -> None:
        """Auto-detect whether notion_id is a page or database and sync it."""
        _report(_pg_prefix() + f"Fetching '{notion_id[:8]}...'")
        try:
            obj_type, title = _resolve_type_and_title(client, notion_id,
                                                       get_page_title, get_database_title)
        except Exception as exc:
            result.errors.append(f"ID {notion_id}: {exc}")
            return

        deck_name = deck_name_for(title, parent_deck_name, deck_root if not parent_deck_name else "")
        deck_id = _register_deck(deck_name)

        if obj_type == "database":
            _report(_pg_prefix() + f"Querying database '{title}'...")
            try:
                pages = client.query_database(notion_id)
            except Exception as exc:
                result.errors.append(f"Database {notion_id}: {exc}")
                return
            _report(_pg_prefix() + f"Found {len(pages)} page{'s' if len(pages) != 1 else ''} in '{title}'")
            for page in pages:
                page_id = page.get("id", "")
                if page_id:
                    _sync_any(page_id, parent_deck_name=deck_name)
        else:
            _report(_pg_prefix() + f"Downloading '{title}'...")
            try:
                blocks = fetch_block_tree(client, notion_id)
            except Exception as exc:
                result.errors.append(f"Blocks {notion_id}: {exc}")
                return
            _add_cards_from_blocks(blocks, deck_id, deck_name)

    total_pages = len(page_ids or [])
    for i, notion_id in enumerate(page_ids or [], start=1):
        if cancel_event and cancel_event.is_set():
            raise SyncCancelledError(result)
        _pg["num"] = i
        _pg["card_n"] = 0
        _pg["card_total"] = 0
        _report(f"Page {i} of {total_pages}  ·  Starting...")
        _before = (result.added, result.updated, result.skipped, len(result.errors))
        _sync_any(notion_id)
        _after = (result.added, result.updated, result.skipped, len(result.errors))
        result.per_page_results[notion_id] = {
            "success": _after[3] == _before[3],
            "added": _after[0] - _before[0],
            "updated": _after[1] - _before[1],
            "skipped": _after[2] - _before[2],
            "error_count": _after[3] - _before[3],
        }

    _report("Saving...")
    save_id_map(id_map)
    return result


def _resolve_type_and_title(client, notion_id: str, get_page_title, get_database_title):
    """Try fetching notion_id as a page first, then as a database.

    Returns ("page"|"database", title_str).
    """
    from .notion.client import NotionError
    try:
        obj = client.get_page(notion_id)
        if obj.get("object") == "page":
            return ("page", get_page_title(obj))
    except NotionError:
        pass

    obj = client.get_database(notion_id)
    return ("database", get_database_title(obj))


def _process_media(card, toggle_block: dict, col,
                   ingest_image, image_block_url,
                   ingest_audio, audio_block_url) -> object:
    """Download images/audio in the toggle's subtree and replace URLs with media filenames."""

    def _collect(blocks: list[dict]) -> list[tuple[str, str]]:
        replacements: list[tuple[str, str]] = []
        for block in blocks:
            btype = block.get("type")
            if btype == "image":
                url = image_block_url(block)
                if url:
                    try:
                        filename = ingest_image(col, url)
                        replacements.append((url, filename))
                    except Exception:
                        pass
            elif btype == "audio":
                url = audio_block_url(block)
                if url:
                    try:
                        filename = ingest_audio(col, url)
                        replacements.append((url, filename))
                    except Exception:
                        pass
            for child in block.get("children", []):
                replacements.extend(_collect([child]))
        return replacements

    for old_url, new_filename in _collect(toggle_block.get("children", [])):
        card.back = card.back.replace(old_url, new_filename)
        card.extra = card.extra.replace(old_url, new_filename)

    return card
