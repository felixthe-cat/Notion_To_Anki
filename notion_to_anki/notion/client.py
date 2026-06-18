"""Thin Notion REST client.

Wraps the official Notion API (https://api.notion.com/v1) using the stdlib (``urllib``).
Sends the ``Authorization: Bearer <token>`` and ``Notion-Version`` headers. Handles JSON
decoding, error responses, and rate-limit (HTTP 429) retry/backoff.

Endpoints used:
  * GET /pages/{id}          → page metadata (title for deck name)
  * GET /blocks/{id}/children → paginated child blocks
"""

from __future__ import annotations

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # TODO(builder): confirm latest stable version header


class NotionClient:
    """Authenticated Notion API client."""

    def __init__(self, token: str) -> None:
        self.token = token

    def get_page(self, page_id: str) -> dict:
        """Return the page object (used for its title)."""
        raise NotImplementedError  # TODO(M2)

    def get_block_children(self, block_id: str) -> list[dict]:
        """Return all child blocks of a block/page, transparently following pagination."""
        raise NotImplementedError  # TODO(M2)
