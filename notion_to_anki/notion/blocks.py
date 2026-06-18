"""Block-tree helpers built on top of :class:`notion.client.NotionClient`.

Notion returns blocks one level at a time; a block with ``has_children`` must be expanded
with a separate request. This module recursively materializes a full tree so converters
can work on plain nested dicts.
"""

from __future__ import annotations


def fetch_block_tree(client, block_id: str) -> list[dict]:
    """Recursively fetch ``block_id``'s children, attaching each block's children inline.

    Returns a list of block dicts where every block with ``has_children`` has a
    ``"children"`` key populated.
    """
    raise NotImplementedError  # TODO(M2)


def get_page_title(page: dict) -> str:
    """Extract a plain-text title from a Notion page object (for the deck name)."""
    raise NotImplementedError  # TODO(M2)
