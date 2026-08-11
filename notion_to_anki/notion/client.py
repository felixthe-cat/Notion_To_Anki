"""Thin Notion REST client using stdlib urllib.

Wraps the official Notion API (https://api.notion.com/v1).
Sends Authorization: Bearer and Notion-Version headers.
Handles JSON decoding, error responses, and 429 retry/backoff.

Endpoints used:
  * GET  /pages/{id}              → page metadata (title for deck name)
  * GET  /databases/{id}          → database metadata (title for deck name)
  * POST /databases/{id}/query    → all pages in a database (paginated)
  * GET  /blocks/{id}/children    → paginated child blocks
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds; doubled on each 429


class NotionError(Exception):
    """Raised when the Notion API returns a non-2xx status code."""


class NotionClient:
    """Authenticated Notion API client.

    check_cancel: optional zero-arg callable invoked before every request and
    during retry back-off. It should raise to abort the run. Every network call
    funnels through _get/_post, so this one hook makes the whole client — block
    tree walks, database pagination, everything — promptly cancellable.
    """

    def __init__(self, token: str, check_cancel=None) -> None:
        self.token = token
        self._check_cancel = check_cancel

    def _cancel_point(self) -> None:
        if self._check_cancel is not None:
            self._check_cancel()

    def _sleep(self, seconds: float) -> None:
        """Back-off that wakes early if the run is cancelled."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._cancel_point()
            time.sleep(min(0.2, deadline - time.monotonic()))

    def get_page(self, page_id: str) -> dict:
        """Return the page object (contains title in properties)."""
        return self._get(f"/pages/{page_id}")

    def get_database(self, database_id: str) -> dict:
        """Return the database object (contains title array)."""
        return self._get(f"/databases/{database_id}")

    def query_database(self, database_id: str) -> list[dict]:
        """Return all pages in a database, transparently following pagination."""
        results: list[dict] = []
        body: dict = {}
        while True:
            data = self._post(f"/databases/{database_id}/query", body=body)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            body["start_cursor"] = data["next_cursor"]
        return results

    def get_block_children(self, block_id: str) -> list[dict]:
        """Return all child blocks, transparently following pagination."""
        results: list[dict] = []
        params: dict = {}
        while True:
            data = self._get(f"/blocks/{block_id}/children", params=params)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            params["start_cursor"] = data["next_cursor"]
        return results

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = NOTION_API_BASE + path
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )

        delay = _RETRY_BASE_DELAY
        for attempt in range(_MAX_RETRIES):
            self._cancel_point()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < _MAX_RETRIES - 1:
                    self._sleep(delay)
                    delay *= 2
                    continue
                body = ""
                try:
                    body = exc.read().decode()
                except Exception:
                    pass
                raise NotionError(f"Notion API {exc.code}: {body}") from exc
        raise NotionError("Max retries exceeded")

    def _post(self, path: str, body: dict | None = None) -> dict:
        url = NOTION_API_BASE + path
        body_bytes = json.dumps(body or {}).encode()
        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        delay = _RETRY_BASE_DELAY
        for attempt in range(_MAX_RETRIES):
            self._cancel_point()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < _MAX_RETRIES - 1:
                    self._sleep(delay)
                    delay *= 2
                    continue
                err_body = ""
                try:
                    err_body = exc.read().decode()
                except Exception:
                    pass
                raise NotionError(f"Notion API {exc.code}: {err_body}") from exc
        raise NotionError("Max retries exceeded")
