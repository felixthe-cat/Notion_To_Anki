"""Notion rich_text / block content → HTML, preserving formatting.

Handles:
  * annotations: bold, italic, strikethrough, underline, code, and color/background
    (mapped to inline ``<b>/<i>/<s>/<u>/<code>`` and CSS classes for colors).
  * links (``text.link.url``).
  * inline equations (rich_text item type ``equation``) → MathJax ``\\( ... \\)``.
  * block-level equation blocks → MathJax ``\\[ ... \\]``.

Colors map to CSS classes (e.g. ``notion-red``, ``notion-blue_background``) defined in the
note type's bundled CSS so they render the same as in Notion.
"""

from __future__ import annotations


def rich_text_to_html(rich_text: list[dict]) -> str:
    """Convert a Notion ``rich_text`` array into an HTML string with formatting preserved."""
    raise NotImplementedError  # TODO(M6)


def block_to_html(block: dict) -> str:
    """Convert a single content block (paragraph, list item, image, equation, ...) to HTML."""
    raise NotImplementedError  # TODO(M6)
