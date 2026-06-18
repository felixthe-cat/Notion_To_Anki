"""Qt UI for the add-on: config dialog and menu actions.

All aqt/Qt imports are deferred inside functions so the module can be imported in
tests without a running Anki.
"""
from __future__ import annotations

_ADDON_NAME = "notion_to_anki"
_autosync_timer = None


# ---------------------------------------------------------------------------
# Config dialog
# ---------------------------------------------------------------------------

def open_config_dialog() -> None:
    """Build and show the configuration dialog. Wired to the Tools menu action."""
    try:
        from aqt import mw  # type: ignore
        from aqt.qt import (  # type: ignore
            QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
            QLabel, QLineEdit, QCheckBox, QSpinBox, QTextEdit,
            QPushButton, QDialogButtonBox,
        )
    except ImportError:
        raise RuntimeError("aqt not available — must be run inside Anki")

    config = mw.addonManager.getConfig(_ADDON_NAME) or {}

    dlg = QDialog(mw)
    dlg.setWindowTitle("Notion → Anki")
    dlg.setMinimumWidth(500)

    root = QVBoxLayout(dlg)

    # ---- Notion credentials ----
    creds = QGroupBox("Notion Integration")
    creds_form = QFormLayout(creds)

    token_edit = QLineEdit(config.get("notion_token", ""))
    token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    token_edit.setPlaceholderText("secret_…")
    creds_form.addRow("Integration token:", token_edit)

    pages_edit = QTextEdit()
    pages_edit.setPlainText("\n".join(config.get("page_ids", [])))
    pages_edit.setPlaceholderText("One Notion page ID per line")
    pages_edit.setMaximumHeight(90)
    creds_form.addRow("Page IDs:", pages_edit)

    deck_root_edit = QLineEdit(config.get("deck_root", ""))
    deck_root_edit.setPlaceholderText("e.g. Notion  (blank = top-level)")
    creds_form.addRow("Deck root:", deck_root_edit)

    root.addWidget(creds)

    # ---- Auto-sync ----
    sync_grp = QGroupBox("Auto-sync (M8)")
    sync_form = QFormLayout(sync_grp)

    auto_check = QCheckBox()
    auto_check.setChecked(config.get("auto_sync_enabled", False))
    sync_form.addRow("Enable auto-sync:", auto_check)

    interval_spin = QSpinBox()
    interval_spin.setRange(1, 1440)
    interval_spin.setValue(config.get("auto_sync_interval_minutes", 15))
    interval_spin.setSuffix(" min")
    sync_form.addRow("Interval:", interval_spin)

    root.addWidget(sync_grp)

    # ---- Button row ----
    btn_row = QHBoxLayout()

    sync_now_btn = QPushButton("Sync now")
    sync_now_btn.clicked.connect(lambda: on_sync_now_clicked(parent=dlg))
    btn_row.addWidget(sync_now_btn)

    btn_row.addStretch()

    std_btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    std_btns.accepted.connect(dlg.accept)
    std_btns.rejected.connect(dlg.reject)
    btn_row.addWidget(std_btns)

    root.addLayout(btn_row)

    if not dlg.exec():
        return

    new_config = {
        "notion_token": token_edit.text().strip(),
        "page_ids": [
            p.strip()
            for p in pages_edit.toPlainText().splitlines()
            if p.strip()
        ],
        "auto_sync_enabled": auto_check.isChecked(),
        "auto_sync_interval_minutes": interval_spin.value(),
        "deck_root": deck_root_edit.text().strip(),
        "on_source_deleted": config.get("on_source_deleted", "ignore"),
    }
    mw.addonManager.writeConfig(_ADDON_NAME, new_config)
    _restart_autosync_timer(new_config)


# ---------------------------------------------------------------------------
# Sync-now handler
# ---------------------------------------------------------------------------

def on_sync_now_clicked(parent=None) -> None:
    """Run a sync in the background and show a result dialog when done."""
    try:
        from aqt import mw  # type: ignore
        from aqt.utils import showInfo, showCritical  # type: ignore
        from aqt.operations import QueryOp  # type: ignore
    except ImportError:
        raise RuntimeError("aqt not available")

    from .sync import run_sync

    def _background(_col) -> object:
        cfg = mw.addonManager.getConfig(_ADDON_NAME) or {}
        return run_sync(col=mw.col, config=cfg)

    def _on_success(result) -> None:
        lines = [
            "Sync complete!",
            f"Added: {result.added}   Updated: {result.updated}   "
            f"Skipped: {result.skipped}",
        ]
        if result.decks_touched:
            lines.append("Decks: " + ", ".join(result.decks_touched))
        if result.errors:
            lines.append(f"\n{len(result.errors)} error(s):")
            lines.extend(result.errors[:5])
        showInfo("\n".join(lines), parent=parent, title="Notion → Anki")

    def _on_failure(exc: Exception) -> None:
        showCritical(str(exc), parent=parent, title="Notion → Anki — Error")

    QueryOp(parent=mw, op=_background, success=_on_success).failure(_on_failure).run_in_background()


# ---------------------------------------------------------------------------
# Auto-sync timer (M8)
# ---------------------------------------------------------------------------

def _restart_autosync_timer(config: dict) -> None:
    """Start (or stop) the QTimer-based auto-sync background loop."""
    global _autosync_timer
    try:
        from aqt.qt import QTimer  # type: ignore
        from aqt import mw  # type: ignore
    except ImportError:
        return

    if _autosync_timer is not None:
        _autosync_timer.stop()
        _autosync_timer = None

    if not config.get("auto_sync_enabled"):
        return

    interval_ms = int(config.get("auto_sync_interval_minutes", 15)) * 60 * 1000
    _autosync_timer = QTimer(mw)
    _autosync_timer.timeout.connect(lambda: on_sync_now_clicked())
    _autosync_timer.start(interval_ms)
