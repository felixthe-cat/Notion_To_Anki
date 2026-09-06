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

import re
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
    # Things worth telling the user that did NOT fail. Kept apart from errors so
    # a clean sync does not announce "8 error(s)" and look broken.
    warnings: list[str] = field(default_factory=list)
    decks_touched: list[str] = field(default_factory=list)
    per_page_results: dict = field(default_factory=dict)  # page_id → result dict
    # Content the card model cannot reach. Only toggles, cloze paragraphs and
    # tables become cards, so an image sitting loose on a page has nothing to
    # attach to. Counting it turns silent loss into something the user can see.
    ignored_images: int = 0
    pages_with_lost_images: int = 0


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
    from .anki_io.writer import (upsert_card, upsert_cloze_card, load_id_map,
                                 save_id_map, index_existing_notes,
                                 load_media_map, save_media_map)

    def _report(msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    result = SyncResult()

    def _check_cancel() -> None:
        """Cancellation point. Passed to the Notion client so that every HTTP
        request and every retry back-off is an opportunity to stop."""
        if cancel_event is not None and cancel_event.is_set():
            raise SyncCancelledError(result)

    _report("Initialising...")
    client = NotionClient(token, check_cancel=_check_cancel)
    model = ensure_model(col)
    cloze_model = ensure_cloze_model(col)
    id_map = load_id_map()
    # Notes already in the collection win over the cached file: the cache can be
    # lost or overwritten, and trusting it alone re-adds every card as a duplicate.
    id_map.update(index_existing_notes(col))
    media_map = load_media_map()

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

    def _deck_getter(name: str):
        """Create the deck lazily, on the first card that needs it.

        Notion trees are mostly navigation: the eMRCS book is 701 pages holding
        123 cards. Creating a deck per page up front left the user with ~700
        empty decks cluttering Anki's deck list.
        """
        holder: dict = {}

        def get() -> int:
            if "id" not in holder:
                holder["id"] = _register_deck(name)
            return holder["id"]

        return get

    def _add_cards_from_blocks(blocks: list[dict], get_deck, deck_name: str) -> None:
        """Convert all card-bearing blocks to notes, then recurse into sub-pages/dbs."""

        toggles = collect_top_level_toggles(blocks)
        # Toggles with an empty header cannot become a card (blank Front). They
        # used to vanish without trace; count them so the summary reflects reality.
        blank = sum(1 for b in blocks
                    if b.get("type") == "toggle"
                    and not b.get("toggle", {}).get("rich_text"))
        if blank:
            result.skipped += blank
            result.warnings.append(
                f"'{deck_name}': {blank} toggle(s) skipped - empty title, no Front for the card"
            )
        clozes  = collect_cloze_blocks(blocks)
        tables  = [b for b in blocks if b.get("type") == "table"]
        total   = len(toggles) + len(clozes) + sum(
            len(t.get("children", [])) for t in tables
        )

        # Images the card model can never reach: anything not inside a toggle
        # subtree. On a page with no toggles at all, that is every image on it.
        reachable_imgs = sum(_count_images([t]) for t in toggles)
        stranded = _count_images(blocks) - reachable_imgs
        if stranded > 0:
            # Count the PAGES that actually lost something, not every card-less
            # page — most of a Notion tree is navigation and losing nothing.
            result.ignored_images += stranded
            result.pages_with_lost_images += 1

        _pg["card_n"] = 0
        _pg["card_total"] = total

        if total:
            _report(_pg_prefix() + f"'{deck_name}'  —  {total} card{'s' if total != 1 else ''}")
        else:
            _report(_pg_prefix() + f"'{deck_name}'  —  scanning...")

        def _card_progress():
            _check_cancel()
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
                if not _has_content(card.front):
                    result.skipped += 1
                    result.warnings.append(
                        f"'{deck_name}': a toggle has an empty question - skipped")
                    continue
                card = _process_media(card, toggle_block, col,
                                      ingest_image, image_block_url,
                                      ingest_audio, audio_block_url,
                                      _check_cancel, result.errors, media_map)
                # An answer-less card cannot be studied. Say which one, so the
                # user can fill it in Notion instead of finding it mid-review.
                if not _has_content(card.back) and not _has_content(card.extra):
                    result.skipped += 1
                    result.warnings.append(
                        f"'{deck_name}': \"{_plain(card.front)}\" has no answer "
                        f"in Notion - card not created")
                    continue
                was_known = card.notion_block_id in id_map
                upsert_card(col, card, get_deck(), model, id_map)
                if was_known:
                    result.updated += 1
                else:
                    result.added += 1
            except SyncCancelledError:
                raise
            except Exception as exc:
                result.errors.append(f"Block {toggle_block.get('id', '?')}: {exc}")

        # 2. Paragraph/heading with {{cN::...}} → Cloze cards
        for cloze_block in clozes:
            _card_progress()
            try:
                card = block_to_cloze_card(cloze_block)
                was_known = card.notion_block_id in id_map
                upsert_cloze_card(col, card, get_deck(), cloze_model, id_map)
                if was_known:
                    result.updated += 1
                else:
                    result.added += 1
            except SyncCancelledError:
                raise
            except Exception as exc:
                result.errors.append(f"Cloze {cloze_block.get('id', '?')}: {exc}")

        # 3. Table → one Basic card per row
        for block in tables:
            for card in table_to_cards(block):
                _card_progress()
                try:
                    was_known = card.notion_block_id in id_map
                    upsert_card(col, card, get_deck(), model, id_map)
                    if was_known:
                        result.updated += 1
                    else:
                        result.added += 1
                except SyncCancelledError:
                    raise
                except Exception as exc:
                    result.errors.append(f"Table row {card.notion_block_id}: {exc}")

        # 4. Recurse into child pages / databases
        for block in blocks:
            _check_cancel()
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
        except SyncCancelledError:
            raise
        except Exception as exc:
            result.errors.append(f"ID {notion_id}: {exc}")
            return

        deck_name = deck_name_for(title, parent_deck_name, deck_root if not parent_deck_name else "")
        get_deck = _deck_getter(deck_name)

        if obj_type == "database":
            _report(_pg_prefix() + f"Querying database '{title}'...")
            try:
                pages = client.query_database(notion_id)
            except SyncCancelledError:
                raise
            except Exception as exc:
                result.errors.append(f"Database {notion_id}: {exc}")
                return
            _report(_pg_prefix() + f"Found {len(pages)} page{'s' if len(pages) != 1 else ''} in '{title}'")
            for page in pages:
                _check_cancel()
                page_id = page.get("id", "")
                if page_id:
                    _sync_any(page_id, parent_deck_name=deck_name)
        else:
            _report(_pg_prefix() + f"Downloading '{title}'...")
            try:
                blocks = fetch_block_tree(client, notion_id)
            except SyncCancelledError:
                raise
            except Exception as exc:
                result.errors.append(f"Blocks {notion_id}: {exc}")
                return
            _add_cards_from_blocks(blocks, get_deck, deck_name)

    total_pages = len(page_ids or [])
    try:
        for i, notion_id in enumerate(page_ids or [], start=1):
            _check_cancel()
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
    finally:
        # Runs on cancellation too: notes already added are in the collection, so
        # their ids must be persisted or the next sync re-adds them as duplicates.
        # Never raise from here — an exception in a finally replaces the one in
        # flight, which would surface a disk error instead of "Import stopped".
        _report("Saving...")
        try:
            save_id_map(id_map)
            save_media_map(media_map)
        except Exception as exc:
            result.errors.append(f"Could not save the synced-card index: {exc}")

    return result


_TAGS = re.compile(r"<[^>]+>")


def _has_content(html: str) -> bool:
    """True if this HTML would actually show the reader something.

    Media counts: a card whose answer is just a diagram is perfectly good. An
    answer that is only empty tags is not — that toggle is empty in Notion.
    """
    if not html:
        return False
    if "<img" in html or "[sound:" in html:
        return True
    return bool(_TAGS.sub("", html).replace("&nbsp;", " ").strip())


def _plain(html: str, limit: int = 60) -> str:
    text = _TAGS.sub("", html).replace("&nbsp;", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _count_images(blocks: list[dict]) -> int:
    """Total image blocks in a block list, including nested children."""
    n = 0
    for block in blocks:
        if block.get("type") == "image":
            n += 1
        n += _count_images(block.get("children", []))
    return n


def _resolve_type_and_title(client, notion_id: str, get_page_title, get_database_title):
    """Try fetching notion_id as a page first, then as a database.

    Returns ("page"|"database", title_str).
    """
    from .notion.client import NotionError
    page_error = None
    try:
        obj = client.get_page(notion_id)
        if obj.get("object") == "page":
            return ("page", get_page_title(obj))
    except NotionError as exc:
        page_error = exc

    try:
        obj = client.get_database(notion_id)
    except NotionError as db_error:
        # Almost everyone pastes a page, so report the page failure. Reporting
        # the database attempt told users their *page* was a missing database.
        raise (page_error or db_error)
    return ("database", get_database_title(obj))


def _process_media(card, toggle_block: dict, col,
                   ingest_image, image_block_url,
                   ingest_audio, audio_block_url,
                   check_cancel=None, errors=None, media_map=None) -> object:
    """Download images/audio in the toggle's subtree and replace URLs with media filenames."""
    import os
    from .convert.richtext import _escape_attr

    def _cancel_point() -> None:
        if check_cancel is not None:
            check_cancel()

    def _fail(kind: str, url: str, exc: Exception) -> None:
        # Silently swallowing these is why broken images looked like a clean sync.
        if errors is not None:
            errors.append(f"{kind} download failed ({url.split('?')[0][-60:]}): {exc}")

    def _cached(block_id: str) -> "str | None":
        """Media filename already downloaded for this image block, if the file
        is still present in the collection."""
        if media_map is None or not block_id:
            return None
        name = media_map.get(block_id)
        if not name:
            return None
        try:
            if os.path.exists(os.path.join(col.media.dir(), name)):
                return name
        except Exception:
            return None
        return None

    def _collect(blocks: list[dict]) -> list[tuple[str, str]]:
        replacements: list[tuple[str, str]] = []
        for block in blocks:
            btype = block.get("type")
            if btype == "image":
                url = image_block_url(block)
                if url:
                    _cancel_point()  # a page of images is otherwise unstoppable
                    hit = _cached(block.get("id", ""))
                    if hit:
                        replacements.append((url, hit))
                        continue
                    try:
                        filename = ingest_image(col, url)
                        replacements.append((url, filename))
                        if media_map is not None and block.get("id"):
                            media_map[block["id"]] = filename
                    except SyncCancelledError:
                        raise
                    except Exception as exc:
                        _fail("Image", url, exc)
            elif btype == "audio":
                url = audio_block_url(block)
                if url:
                    _cancel_point()
                    try:
                        filename = ingest_audio(col, url)
                        replacements.append((url, filename))
                    except SyncCancelledError:
                        raise
                    except Exception as exc:
                        _fail("Audio", url, exc)
            for child in block.get("children", []):
                replacements.extend(_collect([child]))
        return replacements

    for old_url, new_filename in _collect(toggle_block.get("children", [])):
        # The renderer writes the URL into an HTML attribute via _escape_attr, so
        # "&" in Notion's signed S3 links becomes "&amp;". Matching only the raw
        # URL never hit, leaving every image pointing at a URL that expires in an
        # hour. Replace the escaped form too — audio uses the raw form.
        for variant in {_escape_attr(old_url), old_url}:
            card.back = card.back.replace(variant, new_filename)
            card.extra = card.extra.replace(variant, new_filename)

    return card
