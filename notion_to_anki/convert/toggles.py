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

import re
from dataclasses import dataclass

from .richtext import rich_text_to_html, block_to_html, _render_children

_CLOZE_RE = re.compile(r"\{\{c\d+::")


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
    """Filter a block list down to top-level toggle blocks that have non-empty headers.

    Toggles with no rich_text (blank header) are silently skipped — they would
    produce cards with an empty Front, which is never useful.
    """
    return [
        b for b in blocks
        if b.get("type") == "toggle"
        and b.get("toggle", {}).get("rich_text")
    ]


@dataclass
class ClozeCard:
    """A cloze-deletion flashcard. text contains {{c1::...}} syntax."""
    text: str
    back_extra: str
    notion_block_id: str


def collect_cloze_blocks(blocks: list[dict]) -> list[dict]:
    """Return paragraph/heading blocks whose plain text contains {{cN::...}} cloze syntax."""
    result = []
    for block in blocks:
        btype = block.get("type", "")
        if btype in ("paragraph", "heading_1", "heading_2", "heading_3"):
            rt = block.get(btype, {}).get("rich_text", [])
            plain = "".join(r.get("plain_text", "") for r in rt)
            if _CLOZE_RE.search(plain):
                result.append(block)
    return result


def block_to_cloze_card(block: dict) -> ClozeCard:
    """Convert a paragraph/heading block with {{cN::...}} syntax to a ClozeCard."""
    btype = block.get("type", "paragraph")
    rt = block.get(btype, {}).get("rich_text", [])
    # rich_text_to_html preserves {{c1::...}} since braces are not HTML-escaped
    text = rich_text_to_html(rt)
    return ClozeCard(
        text=text,
        back_extra="",
        notion_block_id=block.get("id", ""),
    )


def table_to_cards(table_block: dict) -> list[Card]:
    """Convert a Notion table block to one Card per data row.

    Column 1 → Front, column 2 → Back, column 3 → Extra.
    The header row (if has_column_header is set) is skipped.
    """
    data = table_block.get("table", {})
    has_header = data.get("has_column_header", False)
    children = table_block.get("children", [])

    cards: list[Card] = []
    for i, row in enumerate(children):
        if row.get("type") != "table_row":
            continue
        if has_header and i == 0:
            continue  # skip header row

        cells = row.get("table_row", {}).get("cells", [])

        def cell(idx: int) -> str:
            return rich_text_to_html(cells[idx]) if idx < len(cells) else ""

        front = cell(0)
        if not front.strip():
            continue  # skip blank rows

        cards.append(Card(
            front=front,
            back=cell(1),
            extra=cell(2),
            notion_block_id=row.get("id", ""),
        ))
    return cards


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
