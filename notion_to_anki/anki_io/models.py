"""The custom note type used for synced cards.

Defines / ensures a model named "Notion Toggle (3-field)" with fields:
  Front, Back, Extra  (+ a hidden field or first-field strategy for the Notion block id).

The card template shows Front on the question side, Back + Extra on the answer side, and
bundles CSS that reproduces Notion text/background colors and styles MathJax output.
"""

from __future__ import annotations

MODEL_NAME = "Notion Toggle (3-field)"
FIELDS = ["Front", "Back", "Extra"]


def ensure_model(col):
    """Return the note type, creating it (with templates + CSS) if it doesn't exist."""
    raise NotImplementedError  # TODO(M3)
