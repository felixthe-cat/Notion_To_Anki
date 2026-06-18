"""Idempotent note writing.

Maintains a persistent map ``notion_block_id -> note GUID`` (stored in ``user_files/`` so
it survives add-on updates). On each sync:
  * unseen block id  → add a new note in the target deck
  * known block id   → update the existing note's fields if the source changed
  * never auto-delete; honor the ``on_source_deleted`` config (ignore/suspend/tag)
"""

from __future__ import annotations


def upsert_card(col, card, deck_id: int, model) -> str:
    """Add or update the note for ``card`` in ``deck_id``. Returns the note GUID."""
    raise NotImplementedError  # TODO(M7)


def load_id_map() -> dict[str, str]:
    """Load the persisted notion_block_id → note GUID map from user_files/."""
    raise NotImplementedError  # TODO(M7)


def save_id_map(mapping: dict[str, str]) -> None:
    """Persist the notion_block_id → note GUID map to user_files/."""
    raise NotImplementedError  # TODO(M7)
