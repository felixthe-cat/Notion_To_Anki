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

# Notion allows roughly 3 requests/second. A large page tree is thousands of
# requests, so 429s are routine rather than exceptional and must be waited out:
# giving up on one drops that page's content from the sync.
_RATE_LIMIT_RETRIES = 6
_RETRY_BASE_DELAY = 1.0   # seconds; doubled each time Notion pushes back
_MAX_RETRY_DELAY = 30.0


def _retry_after(exc, fallback: float) -> float:
    """How long to wait before retrying, preferring Notion's own Retry-After."""
    header = None
    try:
        header = exc.headers.get("Retry-After")
    except Exception:
        pass
    if header:
        try:
            return max(0.0, min(float(header), _MAX_RETRY_DELAY))
        except (TypeError, ValueError):
            pass
    return min(fallback, _MAX_RETRY_DELAY)


class NotionError(Exception):
    """Raised when the Notion API returns a non-2xx status code.

    Carries .status and .code so callers can branch, but str() is written for
    the person reading the sync summary, not for a developer.
    """
    def __init__(self, message: str, status: int = 0, code: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


# Notion's own error text is a JSON blob. Users pasted it into bug reports
# because the add-on showed it verbatim; these say what to actually do.
_FRIENDLY = {
    "unauthorized":
        "Notion rejected the integration token. Copy it again from "
        "notion.so/profile/integrations and paste it into the add-on.",
    "restricted_resource":
        "The integration is not allowed to read this page. In Notion, open the "
        "page, click the three-dot menu, choose Connections, and add your "
        "integration.",
    "object_not_found":
        "Notion cannot see this page. Check the ID is right, then in Notion open "
        "the page, click the three-dot menu, choose Connections, and add your "
        "integration - a page stays invisible to the add-on until you do.",
    "validation_error":
        "Notion rejected that ID. It does not look like a valid page or "
        "database ID - paste the page's full URL and let the add-on extract it.",
    "rate_limited":
        "Notion is rate limiting the sync. Wait a minute and run it again.",
}


def _friendly_error(status: int, body: str) -> NotionError:
    """Turn a Notion JSON error body into something a user can act on."""
    code = detail = ""
    try:
        data = json.loads(body)
        code = data.get("code", "") or ""
        detail = data.get("message", "") or ""
    except Exception:
        pass

    text = _FRIENDLY.get(code) or detail or f"Notion returned an error (HTTP {status})."
    return NotionError(text, status=status, code=code)


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

    def _send(self, req) -> dict:
        """Perform a request, waiting out rate limits. Shared by _get and _post."""
        delay = _RETRY_BASE_DELAY
        rate_limited = 0
        while True:
            self._cancel_point()
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and rate_limited < _RATE_LIMIT_RETRIES:
                    rate_limited += 1
                    self._sleep(_retry_after(exc, delay))
                    delay = min(delay * 2, _MAX_RETRY_DELAY)
                    continue
                body = ""
                try:
                    body = exc.read().decode()
                except Exception:
                    pass
                raise _friendly_error(exc.code, body) from exc

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

        return self._send(req)

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
        return self._send(req)
