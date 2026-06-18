"""Toggle tree → flashcard fields.

Core mapping (see docs/PLAN.md §4):
  * A top-level ``toggle`` block becomes one card.
  * Toggle heading rich_text       → Front
  * Toggle's non-toggle children   → Back
  * Toggle's nested ``toggle`` kids → Extra, each wrapped as
        <details><summary>{nested front}</summary>{nested back}</details>
    (nested toggles recurse into their own <details> within Extra).
"""

from __future__ import annotations


class Card:
    """A converted flashcard: front/back/extra HTML plus the source Notion block id."""

    # TODO: fields — front: str, back: str, extra: str, notion_block_id: str
    pass


def toggle_to_card(toggle_block: dict) -> "Card":
    """Convert one top-level toggle block (with children attached) into a :class:`Card`."""
    raise NotImplementedError  # TODO(M3, M4)


def collect_top_level_toggles(blocks: list[dict]) -> list[dict]:
    """Filter a block list down to top-level toggle blocks (skip non-toggle blocks)."""
    raise NotImplementedError  # TODO(M3)
