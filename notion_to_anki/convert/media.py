"""Image/media handling: download from Notion → store in the Anki collection's media.

Notion image blocks expose either ``external.url`` or a time-limited ``file.url`` (which
must be downloaded promptly). Downloaded bytes are written via ``col.media.write_data()``
and referenced in card HTML as ``<img src="{filename}">``. Filenames are content-hashed so
the same image isn't stored twice across re-syncs.
"""

from __future__ import annotations


def ingest_image(col, url: str) -> str:
    """Download an image and write it into the collection media. Returns the media filename."""
    raise NotImplementedError  # TODO(M6)


def image_block_url(block: dict) -> str | None:
    """Return the download URL for a Notion ``image`` block (external or file)."""
    raise NotImplementedError  # TODO(M6)
