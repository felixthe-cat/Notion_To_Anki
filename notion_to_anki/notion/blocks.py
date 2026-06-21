"""Block-tree helpers built on top of NotionClient.

Notion returns blocks one level at a time; a block with has_children must be expanded
with a separate request. This module recursively materialises a full tree so converters
can work on plain nested dicts.
"""
from __future__ import annotations


def fetch_block_tree(client, block_id: str) -> list[dict]:
    """Recursively fetch block_id's children, attaching each block's children inline.

    Returns a list of block dicts where every block with has_children has a
    "children" key populated with its own (recursively fetched) child list.
    """
    blocks = client.get_block_children(block_id)
    for block in blocks:
        if block.get("has_children"):
            block["children"] = fetch_block_tree(client, block["id"])
    return blocks


def get_page_title(page: dict) -> str:
    """Extract a plain-text title from a Notion page object (used as the deck name)."""
    props = page.get("properties", {})

    # The title property is typed "title" regardless of its display name.
    for prop in props.values():
        if prop.get("type") == "title":
            rich_text = prop.get("title", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_text).strip()
            if text:
                return text

    # Fallback for pages whose title can't be found (shouldn't happen for normal pages)
    return "Untitled"


def get_database_title(database: dict) -> str:
    """Extract a plain-text title from a Notion database object."""
    title_arr = database.get("title", [])
    text = "".join(rt.get("plain_text", "") for rt in title_arr).strip()
    return text or "Untitled"
