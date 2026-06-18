"""Toggle tree → flashcard fields.

Core mapping (see docs/PLAN.md §4):
  * A top-level toggle block becomes one card.
  * Toggle heading rich_text         → Front
  * Toggle's non-toggle children     → Back
  * Toggle's nested toggle children  → Extra, each wrapped as
        <details><summary>{nested front}</summary>{nested back}</details>
    (nested toggles recurse deeper within Extra).
"""
from __future__ import annotations

from dataclasses import dataclass

from .richtext import rich_text_to_html, block_to_html, _render_children


@dataclass
class Card:
    """A converted flashcard: front/back/extra HTML plus the source Notion block id."""
    front: str
    back: str
    extra: str
    notion_block_id: str


def toggle_to_card(toggle_block: dict) -> Card:
    """Convert one top-level toggle block (with children already attached) into a Card."""
    data = toggle_block.get("toggle", {})
    front = rich_text_to_html(data.get("rich_text", []))

    children = toggle_block.get("children", [])
    back_blocks: list[dict] = []
    extra_parts: list[str] = []

    for child in children:
        if child.get("type") == "toggle":
            extra_parts.append(_nested_toggle_to_details(child))
        else:
            back_blocks.append(child)

    back = _render_children(back_blocks)
    extra = "".join(extra_parts)

    return Card(
        front=front,
        back=back,
        extra=extra,
        notion_block_id=toggle_block.get("id", ""),
    )


def collect_top_level_toggles(blocks: list[dict]) -> list[dict]:
    """Filter a block list down to top-level toggle blocks (skip all other block types)."""
    return [b for b in blocks if b.get("type") == "toggle"]


def _nested_toggle_to_details(toggle_block: dict) -> str:
    """Recursively render a nested toggle as <details><summary>…</summary>…</details>."""
    data = toggle_block.get("toggle", {})
    nested_front = rich_text_to_html(data.get("rich_text", []))
    children = toggle_block.get("children", [])

    inner_parts: list[str] = []
    for child in children:
        if child.get("type") == "toggle":
            inner_parts.append(_nested_toggle_to_details(child))
        else:
            inner_parts.append(block_to_html(child))

    inner = "".join(inner_parts)
    return f"<details><summary>{nested_front}</summary>{inner}</details>"
