"""Sync orchestration — ties the Notion client, converters, and Anki writer together.

A full sync:
  1. For each configured page ID fetch the page title → deck name.
  2. Fetch the full block tree (recursive).
  3. Collect top-level toggle blocks → convert to Card objects.
  4. Process image blocks inside each card: download + write to collection media.
  5. Recurse into child_page blocks → subdecks (Parent::Child).
  6. Add/update notes idempotently via the block-id → note-id map.

Designed to run off the main thread via aqt QueryOp; only mutates the collection
on the main thread (Anki's own thread-safety rules are respected by the caller).
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
    """Run a full sync. Returns a SyncResult summary.

    Args:
        page_ids: Override the page IDs from config (useful for testing).
        col:      The Anki collection object. Defaults to mw.col if inside Anki.
        config:   Add-on config dict. Defaults to mw.addonManager.getConfig().
    """
    # Resolve collection
    if col is None:
        try:
            from aqt import mw  # type: ignore
            col = mw.col
        except ImportError:
            raise RuntimeError("No collection provided and aqt is not available")

    # Resolve config
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

    # Lazy imports (keep top-level importable without Anki)
    from .notion.client import NotionClient
    from .notion.blocks import fetch_block_tree, get_page_title
    from .convert.toggles import collect_top_level_toggles, toggle_to_card
    from .convert.media import image_block_url, ingest_image
    from .anki_io.models import ensure_model
    from .anki_io.decks import ensure_deck, deck_name_for
    from .anki_io.writer import upsert_card, load_id_map, save_id_map

    client = NotionClient(token)
    model = ensure_model(col)
    result = SyncResult()
    id_map = load_id_map()

    def sync_page(pid: str, parent_deck_name: str | None = None) -> None:
        try:
            page = client.get_page(pid)
            title = get_page_title(page)
            deck_name = deck_name_for(title, parent_deck_name, deck_root)
            deck_id = ensure_deck(col, deck_name)

            if deck_name not in result.decks_touched:
                result.decks_touched.append(deck_name)

            blocks = fetch_block_tree(client, pid)
        except Exception as exc:
            result.errors.append(f"Page {pid}: {exc}")
            return

        # Convert top-level toggles → cards
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
                result.errors.append(
                    f"Block {toggle_block.get('id', '?')}: {exc}"
                )

        # Recurse into child pages → subdecks
        for block in blocks:
            if block.get("type") == "child_page":
                child_id = block.get("id", "")
                if child_id:
                    sync_page(child_id, deck_name)

    for page_id in page_ids:
        sync_page(page_id)

    save_id_map(id_map)
    return result


def _process_images(card, toggle_block: dict, col, ingest_image, image_block_url) -> object:
    """Download images in the toggle's subtree and replace raw URLs with media filenames."""

    def _collect_image_replacements(blocks: list[dict]) -> list[tuple[str, str]]:
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
            children = block.get("children", [])
            if children:
                replacements.extend(_collect_image_replacements(children))
        return replacements

    children = toggle_block.get("children", [])
    for old_url, new_filename in _collect_image_replacements(children):
        card.back = card.back.replace(old_url, new_filename)
        card.extra = card.extra.replace(old_url, new_filename)

    return card
