"""Sync orchestration — ties the Notion client, converters, and Anki writer together.

A full sync works on any mix of Notion page IDs and database IDs:

  Page IDs:
    1. Fetch title → deck name.
    2. Fetch full block tree (recursive).
    3. Top-level toggle blocks → Card objects.
    4. child_page blocks → recurse as subdecks (Parent::Child).
    5. child_database blocks → query database → recurse each entry as subdecks.

  Database IDs (auto-detected):
    1. Fetch database title → deck name.
    2. Query all pages in the database.
    3. For each page: fetch block tree → extract toggles → create cards in a subdeck
       named after the page's title property.

Designed to run off the main thread via aqt QueryOp.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SyncResult:
    """Summary of a completed sync run."""
    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    decks_touched: list[str] = field(default_factory=list)


def run_sync(
    page_ids: list[str] | None = None,
    col=None,
    config: dict | None = None,
) -> SyncResult:
    """Run a full sync. Returns a SyncResult summary."""
    if col is None:
        try:
            from aqt import mw  # type: ignore
            col = mw.col
        except ImportError:
            raise RuntimeError("No collection provided and aqt is not available")

    if config is None:
        try:
            from aqt import mw  # type: ignore
            config = mw.addonManager.getConfig("notion_to_anki") or {}
        except ImportError:
            config = {}

    token: str = config.get("notion_token", "")
    if not token:
        raise ValueError("Notion token is not configured. Open Tools → Notion → Anki.")

    if page_ids is None:
        page_ids = config.get("page_ids", [])

    deck_root: str = config.get("deck_root", "")

    from .notion.client import NotionClient
    from .notion.blocks import fetch_block_tree, get_page_title, get_database_title
    from .convert.toggles import collect_top_level_toggles, toggle_to_card
    from .convert.media import image_block_url, ingest_image
    from .anki_io.models import ensure_model
    from .anki_io.decks import ensure_deck, deck_name_for
    from .anki_io.writer import upsert_card, load_id_map, save_id_map

    client = NotionClient(token)
    model = ensure_model(col)
    result = SyncResult()
    id_map = load_id_map()

    def _register_deck(name: str) -> int:
        did = ensure_deck(col, name)
        if name not in result.decks_touched:
            result.decks_touched.append(name)
        return did

    def _add_cards_from_blocks(blocks: list[dict], deck_id: int, deck_name: str) -> None:
        """Convert top-level toggles in blocks to cards, then recurse into sub-pages/dbs."""
        for toggle_block in collect_top_level_toggles(blocks):
            try:
                card = toggle_to_card(toggle_block)
                card = _process_images(card, toggle_block, col, ingest_image, image_block_url)
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

        for block in blocks:
            btype = block.get("type")
            child_id = block.get("id", "")
            if not child_id:
                continue
            if btype == "child_page":
                _sync_any(child_id, parent_deck_name=deck_name)
            elif btype == "child_database":
                _sync_any(child_id, parent_deck_name=deck_name)

    def _sync_any(notion_id: str, parent_deck_name: str | None = None) -> None:
        """Auto-detect whether notion_id is a page or database and sync it."""
        try:
            obj_type, title = _resolve_type_and_title(client, notion_id,
                                                       get_page_title, get_database_title)
        except Exception as exc:
            result.errors.append(f"ID {notion_id}: {exc}")
            return

        deck_name = deck_name_for(title, parent_deck_name, deck_root if not parent_deck_name else "")
        deck_id = _register_deck(deck_name)

        if obj_type == "database":
            try:
                pages = client.query_database(notion_id)
            except Exception as exc:
                result.errors.append(f"Database {notion_id}: {exc}")
                return
            for page in pages:
                page_id = page.get("id", "")
                if page_id:
                    _sync_any(page_id, parent_deck_name=deck_name)
        else:
            try:
                blocks = fetch_block_tree(client, notion_id)
            except Exception as exc:
                result.errors.append(f"Blocks {notion_id}: {exc}")
                return
            _add_cards_from_blocks(blocks, deck_id, deck_name)

    for notion_id in (page_ids or []):
        _sync_any(notion_id)

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


def _process_images(card, toggle_block: dict, col, ingest_image, image_block_url) -> object:
    """Download images in the toggle's subtree and replace raw URLs with media filenames."""

    def _collect(blocks: list[dict]) -> list[tuple[str, str]]:
        replacements: list[tuple[str, str]] = []
        for block in blocks:
            if block.get("type") == "image":
                url = image_block_url(block)
                if url:
                    try:
                        filename = ingest_image(col, url)
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
