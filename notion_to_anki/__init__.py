"""Notion_To_Anki — Anki add-on entry point.

Loaded by Anki at startup (the folder under ``addons21/`` is imported as a package).
Responsibilities (M1):
  * Register a menu item under Tools → "Notion → Anki".
  * Open the config dialog (see :mod:`notion_to_anki.ui`) where the user stores their
    Notion integration token, page IDs, and auto-sync interval.

Later milestones wire the menu action to :func:`notion_to_anki.sync.run_sync` and start
the optional auto-sync timer.

No top-level Anki imports happen at import time beyond what's needed to register hooks,
so the module stays importable in tests where ``aqt`` may be stubbed.
"""

from __future__ import annotations

# NOTE (builder): import aqt lazily / guard it so unit tests can import submodules
# without a running Anki. Example pattern:
#
#     try:
#         from aqt import mw, gui_hooks
#     except ImportError:
#         mw = None
#
# Then register the menu action and (later) the auto-sync timer here.

# TODO(M1): add a "Notion → Anki" action to the Tools menu that opens the config dialog.
# TODO(M8): on profile load, start the auto-sync timer if enabled in config.
