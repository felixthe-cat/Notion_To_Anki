"""Sync orchestration — ties the Notion client, converters, and Anki writer together.

A full sync:
  1. For each configured page ID, fetch the page (title → deck name) and its block tree.
  2. Walk top-level toggles → convert to {front, back, extra} (see :mod:`convert.toggles`).
  3. Recurse into child_page blocks → subdecks (``Parent::Child``).
  4. Download images into collection media (see :mod:`convert.media`).
  5. Add/update notes idempotently via the block-id → GUID map (see :mod:`anki_io.writer`).

Runs off the main thread; only touches the collection on the main thread.
"""

from __future__ import annotations


def run_sync(page_ids: list[str] | None = None) -> "SyncResult":
    """Run a full sync for the given page IDs (defaults to config). Returns a summary."""
    raise NotImplementedError  # TODO(M3..M7)


class SyncResult:
    """Summary of a sync run: counts of added/updated/skipped notes and any errors."""

    # TODO: fields — added, updated, skipped, errors, decks_touched
    pass
