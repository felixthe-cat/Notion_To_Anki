"""Qt UI for the add-on: config dialog and menu actions.

M1 scope:
  * A config dialog (QDialog) with fields for the Notion token, page IDs, auto-sync
    toggle + interval, and a "Sync now" button.
  * Load values from / save values to Anki's add-on config (``mw.addonManager``).

Keep all ``aqt``/Qt imports inside functions or guarded at module top so the module can
be imported in tests without a running Anki.
"""

from __future__ import annotations


def open_config_dialog() -> None:
    """Build and show the configuration dialog. Wired to the Tools menu action."""
    raise NotImplementedError  # TODO(M1)


def on_sync_now_clicked() -> None:
    """Handler for the dialog's 'Sync now' button → calls sync.run_sync in the background."""
    raise NotImplementedError  # TODO(M3)
