"""Deck / subdeck creation.

Decks are named after Notion page titles. Subpages map to subdecks using Anki's ``::``
separator (e.g. ``Biology::Cells``), optionally under a configured ``deck_root``.
"""

from __future__ import annotations


def ensure_deck(col, full_name: str) -> int:
    """Create the deck (and any missing parents) if needed; return its deck id."""
    raise NotImplementedError  # TODO(M3, M5)


def deck_name_for(page_title: str, parent_full_name: str | None = None) -> str:
    """Build a full deck name from a page title and optional parent deck path."""
    raise NotImplementedError  # TODO(M5)
