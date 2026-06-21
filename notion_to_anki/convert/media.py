"""Image/media handling: download from Notion → store in the Anki collection's media.

Notion image blocks expose either external.url or a time-limited file.url (which
must be downloaded promptly). Downloaded bytes are written via col.media.write_data()
and referenced in card HTML as <img src="{filename}">. Filenames are content-hashed so
the same image isn't stored twice across re-syncs.
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
import urllib.error

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif"}
_ALLOWED_AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".m4a", ".flac", ".opus", ".aac"}


def image_block_url(block: dict) -> str | None:
    """Return the download URL for a Notion image block (external or file)."""
    data = block.get("image", {})
    if "file" in data:
        return data["file"].get("url") or None
    if "external" in data:
        return data["external"].get("url") or None
    return None


def audio_block_url(block: dict) -> str | None:
    """Return the download URL for a Notion audio block (external or file)."""
    data = block.get("audio", {})
    if "file" in data:
        return data["file"].get("url") or None
    if "external" in data:
        return data["external"].get("url") or None
    return None


def ingest_audio(col, url: str) -> str:
    """Download audio and write it into the collection media. Returns the media filename."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "notion-to-anki/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download audio: {exc}") from exc

    digest = hashlib.sha1(data).hexdigest()[:16]
    path_part = url.split("?")[0]
    ext = os.path.splitext(path_part)[1].lower()
    if ext not in _ALLOWED_AUDIO_EXTS:
        ext = ".mp3"

    filename = f"notion_{digest}{ext}"
    col.media.write_data(filename, data)
    return filename


def ingest_image(col, url: str) -> str:
    """Download an image and write it into the collection media. Returns the media filename."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "notion-to-anki/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download image: {exc}") from exc

    digest = hashlib.sha1(data).hexdigest()[:16]

    # derive extension from the URL path (ignore query string)
    path_part = url.split("?")[0]
    ext = os.path.splitext(path_part)[1].lower()
    if ext not in _ALLOWED_EXTS:
        ext = ".jpg"

    filename = f"notion_{digest}{ext}"
    col.media.write_data(filename, data)
    return filename
