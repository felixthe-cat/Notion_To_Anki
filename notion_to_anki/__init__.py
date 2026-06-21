"""Notion_To_Anki — Anki add-on entry point.

Loaded by Anki at startup (the folder under addons21/ is imported as a package).
Responsibilities:
  * Register a "Notion → Anki" action under the Tools menu (M1).
  * On profile load, start the optional auto-sync timer if enabled (M8).

aqt imports are guarded so the package stays importable in unit tests where Anki
is not present.
"""
from __future__ import annotations

try:
    from aqt import mw, gui_hooks  # type: ignore
    from aqt.qt import QAction  # type: ignore

    def _open_dialog() -> None:
        from .ui import open_config_dialog
        open_config_dialog()

    def _setup_menu() -> None:
        action = QAction("NotionSync for Anki", mw)
        action.triggered.connect(_open_dialog)
        mw.form.menuTools.addAction(action)

    def _on_profile_loaded() -> None:
        import os
        from .ui import _restart_autosync_timer
        try:
            _name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
            config = mw.addonManager.getConfig(_name) or {}
        except Exception:
            config = {}
        _restart_autosync_timer(config)

    gui_hooks.main_window_did_init.append(_setup_menu)
    gui_hooks.profile_did_open.append(_on_profile_loaded)

except ImportError:
    # Outside Anki (tests) — nothing to register.
    pass
