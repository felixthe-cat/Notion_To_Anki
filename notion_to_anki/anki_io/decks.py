"""Deck / subdeck creation.

Decks are named after Notion page titles. Subpages map to subdecks using Anki's ::
separator (e.g. Biology::Cells), optionally under a configured deck_root.
"""
from __future__ import annotations


def ensure_deck(col, full_name: str) -> int:
    """Create the deck (and any missing parents) if needed; return its deck id."""
    did = col.decks.id(full_name)
    col.decks.flush()
    return did


def deck_name_for(
    page_title: str,
    parent_full_name: str | None = None,
    deck_root: str = "",
) -> str:
    """Build a full deck name from a page title and optional parent deck path.

    Anki uses :: as the hierarchy separator; we replace any literal :: in the
    Notion page title with an em-dash so they don't accidentally split the name.
    """
    safe_title = page_title.replace("::", "—")  # em-dash

    if parent_full_name:
        return f"{parent_full_name}::{safe_title}"
    if deck_root:
        return f"{deck_root}::{safe_title}"
    return safe_title
