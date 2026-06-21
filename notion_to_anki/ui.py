"""Qt UI for the add-on: config dialog and menu actions.

All aqt/Qt imports are deferred inside functions so the module can be imported in
tests without a running Anki.
"""
from __future__ import annotations

import os as _os
_ADDON_NAME = _os.path.basename(_os.path.dirname(_os.path.abspath(__file__)))
_autosync_timer = None


# ---------------------------------------------------------------------------
# Sync status persistence (written to user_files/last_sync_status.json)
# ---------------------------------------------------------------------------

def _status_file_path() -> str:
    pkg_dir = _os.path.dirname(_os.path.abspath(__file__))
    user_files = _os.path.join(_os.path.dirname(pkg_dir), "user_files")
    _os.makedirs(user_files, exist_ok=True)
    return _os.path.join(user_files, "last_sync_status.json")


def _save_sync_status(success: bool, added: int = 0, updated: int = 0,
                      skipped: int = 0, errors=None, error_msg: str = "",
                      per_page_results: "dict | None" = None) -> None:
    import json
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    data = {
        "timestamp": ts,
        "success": success,
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "errors": errors or [],
        "error_msg": error_msg,
    }
    if per_page_results:
        data["per_page"] = {pid: {**r, "timestamp": ts} for pid, r in per_page_results.items()}
    try:
        with open(_status_file_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _load_sync_status() -> "dict | None":
    import json
    path = _status_file_path()
    if not _os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _status_display(status: "dict | None") -> "tuple[str, str]":
    """Return (display_text, hex_colour) for the last-sync status label."""
    if status is None:
        return "Never synced", "#7F8C8D"
    ts = status.get("timestamp", "?")
    if status.get("success"):
        a = status.get("added", 0)
        u = status.get("updated", 0)
        s = status.get("skipped", 0)
        errs = status.get("errors", [])
        text = f"✓  {ts}  ·  Added: {a}  ·  Updated: {u}  ·  Skipped: {s}"
        if errs:
            text += f"  ·  {len(errs)} warning(s)"
            return text, "#E67E22"
        return text, "#27AE60"
    msg = (status.get("error_msg", "Unknown error") or "Unknown error")[:80]
    return f"✗  {ts}  ·  {msg}", "#E74C3C"


def _set_page_status_item(table, row: int, page_id: str, per_page: dict) -> None:
    """Populate column 1 of the pages table with the per-page sync status."""
    try:
        from aqt.qt import QTableWidgetItem, QColor, Qt  # type: ignore
    except ImportError:
        return
    ps = per_page.get(page_id)
    if ps is None:
        item = QTableWidgetItem("Not synced")
        item.setForeground(QColor("#7F8C8D"))
    elif ps.get("success"):
        ts = ps.get("timestamp", "")
        time_str = ts[-5:] if len(ts) >= 5 else ts  # HH:MM
        a = ps.get("added", 0)
        u = ps.get("updated", 0)
        ec = ps.get("error_count", 0)
        if a > 0:
            text = f"✓ {time_str}  ·  {a} new"
        elif u > 0:
            text = f"✓ {time_str}  ·  updated"
        else:
            text = f"✓ {time_str}  ·  up to date"
        item = QTableWidgetItem(text)
        item.setForeground(QColor("#E67E22" if ec > 0 else "#27AE60"))
    else:
        ts = ps.get("timestamp", "")
        time_str = ts[-5:] if len(ts) >= 5 else ts
        item = QTableWidgetItem(f"✗ {time_str}  ·  failed")
        item.setForeground(QColor("#E74C3C"))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    table.setItem(row, 1, item)

# ---------------------------------------------------------------------------
# Colour palette (matches the reference screenshot style)
# ---------------------------------------------------------------------------
_SYNC_INTERVALS = [
    ("Every minute",     1),
    ("Every 5 minutes",  5),
    ("Every 15 minutes", 15),
    ("Every 30 minutes", 30),
    ("Every hour",       60),
    ("Every 6 hours",    360),
    ("Every day",        1440),
    ("Every week",       10080),
    ("Every month",      43200),
]

_BTN_GREEN  = "background-color:#27AE60;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;"
_BTN_BLUE   = "background-color:#2980B9;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;"
_BTN_RED    = "background-color:#E74C3C;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;"
_BTN_GREY   = "background-color:#7F8C8D;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;"
_BTN_TEAL   = "background-color:#16A085;color:white;border-radius:4px;padding:6px 14px;font-weight:bold;"
_BTN_HELP   = (
    "QPushButton{background-color:#2980B9;color:white;border-radius:13px;"
    "font-weight:bold;font-size:14px;min-width:26px;min-height:26px;"
    "padding:0px;text-align:center;}"
    "QPushButton:hover{background-color:#1A5276;}"
)
_BTN_SHOW   = (
    "QPushButton{background:#BDC3C7;color:#2C3E50;border:1px solid #95A5A6;"
    "border-radius:3px;font-size:11px;font-weight:bold;padding:2px 5px;}"
    "QPushButton:checked{background:#95A5A6;}"
)

# ---------------------------------------------------------------------------
# HTML content for help pop-ups
# ---------------------------------------------------------------------------
def _token_help_html() -> str:
    """Build the integration token help HTML with embedded screenshots."""
    import os
    shots_dir = os.path.join(os.path.dirname(__file__), "screenshots")

    def img(filename: str) -> str:
        path = os.path.join(shots_dir, filename)
        if os.path.isfile(path):
            url = "file:///" + path.replace("\\", "/").lstrip("/")
            return (
                f'<p style="margin:6px 0 10px 0;">'
                f'<img src="{url}" '
                f'style="width:100%;max-width:500px;border-radius:4px;'
                f'border:1px solid #BDC3C7;display:block;">'
                f'</p>'
            )
        return (
            f'<p style="margin:6px 0 10px 0;">'
            f'<div style="background:#F2F3F4;padding:8px;border-radius:4px;'
            f'font-size:12px;">&#128248; <i>[{filename}]</i></div>'
            f'</p>'
        )

    return (
        '<html><body style="font-family:Arial,sans-serif;font-size:13px;color:#2C3E50;">'

        '<h2 style="color:#2980B9;">&#128273; How to get your Notion Integration Token</h2>'
        '<p>Your integration token lets this add-on read your Notion pages. Follow these four steps:</p>'
        '<hr/>'

        '<h3>Step 1 &#8212; Go to the Notion Connections page</h3>'
        '<div style="background:#EBF5FB;border-left:4px solid #2980B9;padding:10px;border-radius:4px;margin:8px 0;">'
        'Visit <a href="https://www.notion.so/profile/integrations">notion.so/profile/integrations</a><br/>'
        'Click <b>"+ New connection"</b> in the top-right corner.'
        '</div>'
        + img("Screenshot Notion Integrations page.png") +

        '<h3>Step 2 &#8212; Create the connection</h3>'
        '<div style="background:#EBF5FB;border-left:4px solid #2980B9;padding:10px;border-radius:4px;margin:8px 0;">'
        '&#8226; Enter a <b>Connection name</b> (e.g. "Anki")<br/>'
        '&#8226; Leave <b>Authentication method</b> as <b>Access token</b><br/>'
        '&#8226; Select your workspace under <b>Installable in</b><br/>'
        '&#8226; Click <b>"Create connection"</b>'
        '</div>'
        + img("Integration creation form with Name field filled in.png") +

        '<h3>Step 3 &#8212; Copy the Access Token</h3>'
        '<div style="background:#EBF5FB;border-left:4px solid #2980B9;padding:10px;border-radius:4px;margin:8px 0;">'
        'On the connection page, find the <b>Integration token</b> section.<br/>'
        'Click the <b>copy icon</b> next to the hidden token and paste it into this add-on.'
        '</div>'
        + img("Integration secrets section with Copy button highlighted.png") +

        '<h3>Step 4 &#8212; Connect the integration to your Notion pages</h3>'
        '<div style="background:#FDEBD0;border-left:4px solid #E67E22;padding:10px;border-radius:4px;margin:8px 0;">'
        '&#9888; <b>Important:</b> the integration can only read pages you explicitly connect it to.<br/><br/>'
        'For each page you want to sync:<br/>'
        '1. Open the page in Notion<br/>'
        '2. Click the <b>&#8943; (three-dot)</b> menu &#8198;&#10102; at the top-right<br/>'
        '3. Click <b>"Connections"</b> &#10103;<br/>'
        '4. Find and click your integration name &#10104; to connect it'
        '</div>'
        + img("Adding Connector to Notion Page.png") +

        '<p style="color:#7F8C8D;font-size:11px;">'
        'Need more help? Visit '
        '<a href="https://developers.notion.com/docs/create-a-notion-integration">'
        'developers.notion.com/docs/create-a-notion-integration</a>'
        '</p>'

        '</body></html>'
    )

_PAGEID_HELP_HTML = """
<html><body style="font-family:Arial,sans-serif;font-size:13px;color:#2C3E50;">

<h2 style="color:#27AE60;">&#128196; How to find your Notion Page ID</h2>

<p>The Page ID tells the add-on which Notion pages to import cards from.</p>

<hr/>

<h3>Method A &#8212; From the browser URL (easiest)</h3>
<div style="background:#EAFAF1;border-left:4px solid #27AE60;padding:10px;border-radius:4px;margin:8px 0;">
  Open your Notion page in a <b>browser</b> (not the desktop app).<br/><br/>
  The URL looks like:<br/>
  <span style="font-family:monospace;font-size:12px;">https://www.notion.so/<b>My-Page-Title-</b><span style="color:#E74C3C;font-weight:bold;">a1b2c3d4e5f6...</span></span><br/><br/>
  The <span style="color:#E74C3C;font-weight:bold;">32-character string</span> at the very end (after the last dash) is your Page ID.
</div>
<div style="background:#F2F3F4;padding:8px;border-radius:4px;margin:4px 0;font-size:12px;">
  &#128248; <i>[Screenshot: Browser address bar with the page ID portion highlighted in red]</i>
</div>

<h3>Method B &#8212; Desktop app (three-dot menu)</h3>
<div style="background:#EAFAF1;border-left:4px solid #27AE60;padding:10px;border-radius:4px;margin:8px 0;">
  1. Open the page in the Notion desktop app<br/>
  2. Click the <b>&#8943; (three dots)</b> menu at the top-right<br/>
  3. Click <b>"Copy link"</b><br/>
  4. Paste it here &#8212; the add-on will extract the 32-character ID from the URL automatically
</div>
<div style="background:#F2F3F4;padding:8px;border-radius:4px;margin:4px 0;font-size:12px;">
  &#128248; <i>[Screenshot: Notion desktop three-dot menu with &quot;Copy link&quot; option highlighted]</i>
</div>

<h3>Formatting in this dialog</h3>
<div style="background:#EBF5FB;border-left:4px solid #2980B9;padding:10px;border-radius:4px;margin:8px 0;">
  Enter <b>one Page ID per line</b> in the text box.<br/>
  You can paste the full URL &#8212; the add-on extracts the ID automatically.<br/><br/>
  Example:<br/>
  <span style="font-family:monospace;">a1b2c3d4e5f6789012345678901234ab<br/>
  https://www.notion.so/My-Notes-cc1122...</span>
</div>

<p style="color:#7F8C8D;font-size:11px;">
  Tip: if you add a <b>parent page</b>, all child pages are synced too (enable Recursive in settings).
</p>

</body></html>
"""

_DECK_HELP_HTML = """
<html><body style="font-family:Arial,sans-serif;font-size:13px;color:#2C3E50;">

<h2 style="color:#8E44AD;">🗂 Deck Root</h2>

<p>Cards from Notion are placed into Anki decks that mirror your Notion page hierarchy.</p>

<div style="background:#F5EEF8;border-left:4px solid #8E44AD;padding:10px;border-radius:4px;margin:8px 0;">
  <b>Leave blank</b> → cards go into top-level decks named after your Notion pages.<br/><br/>
  <b>Set a prefix</b> (e.g. <tt>Notion</tt>) → all decks are nested under that prefix:<br/>
  &nbsp;&nbsp;<tt>Notion::My Page::Sub-page</tt>
</div>

<p>This is useful if you want to keep Notion-imported cards separate from your other Anki decks.</p>

</body></html>
"""


_FORMAT_GUIDE_HTML = """
<html><body style="font-family:Arial,sans-serif;font-size:13px;color:#2C3E50;">

<h2 style="color:#16A085;">&#128203; How to Format Your Notion Page</h2>
<p>
  This add-on scans your Notion page for three types of blocks and converts each one
  into an Anki flashcard. Everything else on the page is ignored.
</p>
<hr/>

<!-- ============================================================ -->
<h3 style="color:#2980B9;">Format 1 &mdash; Toggle Q&amp;A <span style="font-weight:normal;font-size:11px;color:#7F8C8D;">(recommended)</span></h3>

<p>
  Create a <b>toggle block</b> in Notion.<br/>
  &#8226; The <b>toggle title</b> becomes the card <b>Front</b> (question).<br/>
  &#8226; Everything <b>inside</b> the toggle becomes the card <b>Back</b> (answer).
</p>

<div style="background:#F4F6F7;border:1px solid #D5D8DC;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#7F8C8D;margin-bottom:6px;font-weight:bold;">NOTION PAGE</div>
  <div style="background:white;border-radius:4px;padding:8px 10px;border:1px solid #E5E7E9;font-size:13px;">
    <span style="color:#888;">&#9660;</span> <b>What are the phases of mitosis?</b>
    <div style="padding-left:18px;margin-top:6px;">
      <ul style="margin:0;padding-left:16px;">
        <li>Prophase</li>
        <li>Metaphase</li>
        <li>Anaphase</li>
        <li>Telophase</li>
      </ul>
    </div>
  </div>
</div>

<div style="background:#EBF5FB;border:1px solid #AED6F1;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#2980B9;margin-bottom:8px;font-weight:bold;">ANKI CARD PRODUCED</div>
  <table width="100%" style="border-collapse:collapse;font-size:12px;">
    <tr>
      <th style="background:#D6EAF8;padding:5px 8px;border:1px solid #AED6F1;text-align:left;">Front</th>
      <th style="background:#D6EAF8;padding:5px 8px;border:1px solid #AED6F1;text-align:left;">Back</th>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #AED6F1;vertical-align:top;">What are the phases of mitosis?</td>
      <td style="padding:5px 8px;border:1px solid #AED6F1;">&#8226; Prophase<br/>&#8226; Metaphase<br/>&#8226; Anaphase<br/>&#8226; Telophase</td>
    </tr>
  </table>
</div>

<h4 style="margin-bottom:4px;">Collapsible hints with nested toggles</h4>
<p>
  Place a <b>toggle inside the answer</b> to create a collapsible hint on the back of the card.
  The nested toggle must be indented <i>under</i> the parent toggle in Notion.
</p>
<div style="background:#F4F6F7;border:1px solid #D5D8DC;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#7F8C8D;margin-bottom:6px;font-weight:bold;">NOTION PAGE</div>
  <div style="background:white;border-radius:4px;padding:8px 10px;border:1px solid #E5E7E9;font-size:13px;">
    <span style="color:#888;">&#9660;</span> <b>What are the phases of mitosis?</b>
    <div style="padding-left:22px;margin-top:6px;border-left:2px solid #E5E7E9;">
      <div>There are <b>4 phases</b>.</div>
      <div style="margin-top:6px;">
        <span style="color:#888;">&#9658;</span> <i>Mnemonic (click to reveal)</i>
        <div style="padding-left:22px;margin-top:2px;border-left:2px solid #E5E7E9;color:#888;font-size:12px;">
          PMAT &mdash; Prophase, Metaphase, Anaphase, Telophase
        </div>
      </div>
    </div>
  </div>
</div>

<div style="background:#EBF5FB;border:1px solid #AED6F1;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#2980B9;margin-bottom:8px;font-weight:bold;">ANKI CARD PRODUCED</div>
  <table width="100%" style="border-collapse:collapse;font-size:12px;">
    <tr>
      <th style="background:#D6EAF8;padding:5px 8px;border:1px solid #AED6F1;text-align:left;">Front</th>
      <th style="background:#D6EAF8;padding:5px 8px;border:1px solid #AED6F1;text-align:left;">Back</th>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #AED6F1;vertical-align:top;">What are the phases of mitosis?</td>
      <td style="padding:5px 8px;border:1px solid #AED6F1;vertical-align:top;">
        There are <b>4 phases</b>.<br/><br/>
        <span style="background:#F4F6F7;border:1px solid #D5D8DC;border-radius:3px;padding:3px 6px;font-size:11px;">
          &#9658; <i>Mnemonic (click to reveal)</i>
        </span>
        <div style="padding-left:10px;margin-top:4px;color:#888;font-size:11px;font-style:italic;">
          &rarr; expands to show: PMAT &mdash; Prophase, Metaphase, Anaphase, Telophase
        </div>
      </td>
    </tr>
  </table>
</div>

<h4 style="margin-bottom:4px;">Supported rich text in the answer</h4>
<p style="font-size:12px;">
  <b>Bold</b> &nbsp;&#8226;&nbsp; <i>Italic</i> &nbsp;&#8226;&nbsp;
  <code>Inline code</code> &nbsp;&#8226;&nbsp; <s>Strikethrough</s> &nbsp;&#8226;&nbsp;
  Underline &nbsp;&#8226;&nbsp; Colour highlights &nbsp;&#8226;&nbsp;
  Bullet &amp; numbered lists &nbsp;&#8226;&nbsp; Headings &nbsp;&#8226;&nbsp;
  Images &nbsp;&#8226;&nbsp; Code blocks &nbsp;&#8226;&nbsp;
  Math equations (LaTeX via MathJax: <code>\\(x^2\\)</code>) &nbsp;&#8226;&nbsp;
  Callouts &nbsp;&#8226;&nbsp; Quotes &nbsp;&#8226;&nbsp; Dividers
</p>

<hr/>

<!-- ============================================================ -->
<h3 style="color:#E67E22;">Format 2 &mdash; Cloze Deletion</h3>

<p>
  Type <b><code>{{c1::your answer}}</code></b> anywhere inside a <b>paragraph or heading</b>.
  Anki will blank out that part and ask you to recall it.<br/><br/>
  Use different numbers (<code>c1</code>, <code>c2</code>, &hellip;) for multiple blanks in one sentence.
</p>

<div style="background:#F4F6F7;border:1px solid #D5D8DC;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#7F8C8D;margin-bottom:6px;font-weight:bold;">NOTION PAGE (paragraph)</div>
  <div style="background:white;border-radius:4px;padding:8px 10px;border:1px solid #E5E7E9;font-size:13px;">
    The {{c1::mitochondria}} is the powerhouse of the {{c2::cell}}.
  </div>
</div>

<div style="background:#FEF9E7;border:1px solid #F9E79F;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#D4AC0D;margin-bottom:8px;font-weight:bold;">ANKI CLOZE CARDS PRODUCED</div>
  <table width="100%" style="border-collapse:collapse;font-size:12px;">
    <tr>
      <th style="background:#FCF3CF;padding:5px 8px;border:1px solid #F9E79F;text-align:left;">Card</th>
      <th style="background:#FCF3CF;padding:5px 8px;border:1px solid #F9E79F;text-align:left;">What Anki shows</th>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #F9E79F;">Card 1 (c1)</td>
      <td style="padding:5px 8px;border:1px solid #F9E79F;">The <b>[...]</b> is the powerhouse of the cell.</td>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #F9E79F;">Card 2 (c2)</td>
      <td style="padding:5px 8px;border:1px solid #F9E79F;">The mitochondria is the powerhouse of the <b>[...]</b>.</td>
    </tr>
  </table>
</div>

<div style="background:#FDEBD0;border-left:4px solid #E67E22;padding:8px 12px;border-radius:4px;margin:8px 0;font-size:12px;">
  &#9888; Cloze cards are <b>not</b> created from toggle blocks &mdash; only from plain paragraphs and headings.
</div>

<hr/>

<!-- ============================================================ -->
<h3 style="color:#27AE60;">Format 3 &mdash; Table</h3>

<p>
  Create a <b>Notion table</b> on your page. Each data row becomes one card:
</p>

<div style="background:#F4F6F7;border:1px solid #D5D8DC;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#7F8C8D;margin-bottom:6px;font-weight:bold;">NOTION TABLE</div>
  <table width="100%" style="border-collapse:collapse;font-size:12px;background:white;">
    <tr style="background:#E8DAEF;">
      <th style="padding:5px 8px;border:1px solid #D5D8DC;text-align:left;">Front (col 1)</th>
      <th style="padding:5px 8px;border:1px solid #D5D8DC;text-align:left;">Back (col 2)</th>
      <th style="padding:5px 8px;border:1px solid #D5D8DC;text-align:left;">Extra (col 3, optional)</th>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #D5D8DC;">What is ATP?</td>
      <td style="padding:5px 8px;border:1px solid #D5D8DC;">Adenosine triphosphate</td>
      <td style="padding:5px 8px;border:1px solid #D5D8DC;">Energy currency of the cell</td>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #D5D8DC;">What does DNA stand for?</td>
      <td style="padding:5px 8px;border:1px solid #D5D8DC;">Deoxyribonucleic acid</td>
      <td style="padding:5px 8px;border:1px solid #D5D8DC;"></td>
    </tr>
  </table>
</div>

<div style="background:#EAFAF1;border:1px solid #A9DFBF;border-radius:6px;padding:10px 14px;margin:8px 0;">
  <div style="font-size:11px;color:#27AE60;margin-bottom:8px;font-weight:bold;">ANKI CARDS PRODUCED</div>
  <table width="100%" style="border-collapse:collapse;font-size:12px;">
    <tr>
      <th style="background:#D5F5E3;padding:5px 8px;border:1px solid #A9DFBF;text-align:left;">Front</th>
      <th style="background:#D5F5E3;padding:5px 8px;border:1px solid #A9DFBF;text-align:left;">Back</th>
      <th style="background:#D5F5E3;padding:5px 8px;border:1px solid #A9DFBF;text-align:left;">Extra</th>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #A9DFBF;vertical-align:top;">What is ATP?</td>
      <td style="padding:5px 8px;border:1px solid #A9DFBF;vertical-align:top;">Adenosine triphosphate</td>
      <td style="padding:5px 8px;border:1px solid #A9DFBF;vertical-align:top;">Energy currency of the cell</td>
    </tr>
    <tr>
      <td style="padding:5px 8px;border:1px solid #A9DFBF;vertical-align:top;">What does DNA stand for?</td>
      <td style="padding:5px 8px;border:1px solid #A9DFBF;vertical-align:top;">Deoxyribonucleic acid</td>
      <td style="padding:5px 8px;border:1px solid #A9DFBF;vertical-align:top;color:#888;font-style:italic;">(blank)</td>
    </tr>
  </table>
</div>

<div style="background:#EAFAF1;border-left:4px solid #27AE60;padding:8px 12px;border-radius:4px;margin:8px 0;font-size:12px;">
  &#8226; Enable <b>Header row</b> in Notion (the table menu) &mdash; the add-on will skip it automatically.<br/>
  &#8226; Column 3 is optional. Leave it blank to skip the Extra field.<br/>
  &#8226; Rows with an empty Front cell are skipped.
</div>

<hr/>
<p style="color:#7F8C8D;font-size:11px;">
  Tip: you can mix all three formats on the same Notion page &mdash; each block type is processed independently.
</p>

</body></html>
"""


# ---------------------------------------------------------------------------
# Helper — circular ? button
# ---------------------------------------------------------------------------

def _help_btn(parent, html_content: str):
    """Return a small circular blue '?' button that opens a help dialog."""
    try:
        from aqt.qt import QPushButton, QDialog, QVBoxLayout, QTextBrowser, QPushButton as Btn  # type: ignore
    except ImportError:
        return None

    btn = QPushButton("?", parent)
    btn.setFixedSize(26, 26)
    btn.setStyleSheet(_BTN_HELP)
    btn.setToolTip("Click for help")

    def _show_help():
        dlg = QDialog(parent)
        dlg.setWindowTitle("Help")
        dlg.setMinimumSize(540, 460)
        lay = QVBoxLayout(dlg)

        browser = QTextBrowser()
        browser.setHtml(html_content)
        browser.setOpenExternalLinks(True)
        lay.addWidget(browser)

        close_btn = Btn("Close")
        close_btn.setStyleSheet(_BTN_GREY)
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)

        dlg.exec()

    btn.clicked.connect(_show_help)
    return btn


# ---------------------------------------------------------------------------
# Helper — labelled row with optional help button
# ---------------------------------------------------------------------------

def _form_row(form_layout, label_text: str, widget, help_btn_widget=None):
    """Add a row to a QFormLayout; if a help button is provided, wrap the widget."""
    try:
        from aqt.qt import QHBoxLayout, QWidget  # type: ignore
    except ImportError:
        form_layout.addRow(label_text, widget)
        return

    if help_btn_widget is None:
        form_layout.addRow(label_text, widget)
        return

    container = QWidget()
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addWidget(help_btn_widget)
    form_layout.addRow(label_text, container)


# ---------------------------------------------------------------------------
# Config dialog
# ---------------------------------------------------------------------------

def open_config_dialog() -> None:
    """Build and show the configuration dialog. Wired to the Tools menu action."""
    try:
        from aqt import mw  # type: ignore
        from aqt.qt import (  # type: ignore
            QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
            QLabel, QLineEdit, QCheckBox, QComboBox,
            QPushButton, QDialogButtonBox, QWidget, Qt,
            QTableWidget, QTableWidgetItem, QHeaderView,
        )
    except ImportError:
        raise RuntimeError("aqt not available — must be run inside Anki")

    config = mw.addonManager.getConfig(_ADDON_NAME) or {}

    dlg = QDialog(mw)
    dlg.setWindowTitle("NotionSync for Anki  ·  Configuration")
    dlg.setMinimumWidth(520)

    root = QVBoxLayout(dlg)
    root.setSpacing(10)

    # ---- Header label ----
    header = QLabel(
        "<span style='font-size:15px;font-weight:bold;color:#2C3E50;'>"
        "NotionSync for Anki</span>"
        "<span style='font-size:11px;color:#7F8C8D;'>&nbsp; Sync your Notion pages to Anki flashcards</span>"
    )
    header.setTextFormat(Qt.TextFormat.RichText)
    root.addWidget(header)

    # ---- Notion credentials ----
    creds = QGroupBox("Notion Integration")
    creds.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;}")
    creds_form = QFormLayout(creds)
    creds_form.setVerticalSpacing(8)

    # Token row — password field + show/hide toggle + help button
    token_container = QWidget()
    token_row = QHBoxLayout(token_container)
    token_row.setContentsMargins(0, 0, 0, 0)

    token_edit = QLineEdit(config.get("notion_token", ""))
    token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    token_edit.setPlaceholderText("secret_…")
    token_row.addWidget(token_edit)

    show_btn = QPushButton("Show")
    show_btn.setFixedWidth(50)
    show_btn.setCheckable(True)
    show_btn.setStyleSheet(_BTN_SHOW)

    def _toggle_echo(checked):
        token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )
        show_btn.setText("Hide" if checked else "Show")

    show_btn.toggled.connect(_toggle_echo)
    token_row.addWidget(show_btn)
    token_row.addWidget(_help_btn(dlg, _token_help_html()))

    creds_form.addRow("Integration token:", token_container)

    # Page IDs — table with per-row add / delete
    pages_outer = QWidget()
    pages_vbox = QVBoxLayout(pages_outer)
    pages_vbox.setContentsMargins(0, 0, 0, 0)
    pages_vbox.setSpacing(4)

    pages_table = QTableWidget(0, 2)
    pages_table.setHorizontalHeaderLabels(["Page ID / URL", "Last Sync"])
    pages_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    pages_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    pages_table.setColumnWidth(1, 175)
    pages_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    pages_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    pages_table.setMinimumHeight(90)
    pages_table.setMaximumHeight(140)
    pages_table.verticalHeader().setVisible(False)
    pages_table.setStyleSheet(
        "QTableWidget{border:1px solid #BDC3C7;border-radius:3px;}"
        "QHeaderView::section{background:#ECF0F1;font-weight:bold;padding:4px;border:none;border-bottom:1px solid #BDC3C7;}"
    )
    _sync_status_on_open = _load_sync_status()
    _per_page_on_open = (_sync_status_on_open or {}).get("per_page", {})
    for pid in config.get("page_ids", []):
        r = pages_table.rowCount()
        pages_table.insertRow(r)
        pages_table.setItem(r, 0, QTableWidgetItem(pid))
        _set_page_status_item(pages_table, r, pid, _per_page_on_open)

    pages_vbox.addWidget(pages_table)

    # Input + Add / Delete row
    ctrl_row = QHBoxLayout()
    ctrl_row.setSpacing(6)

    page_input = QLineEdit()
    page_input.setPlaceholderText("Paste Page ID or full Notion URL and press Add...")
    ctrl_row.addWidget(page_input, stretch=1)

    add_page_btn = QPushButton("Add Item")
    add_page_btn.setStyleSheet(_BTN_GREEN)

    def _add_page_row():
        raw = page_input.text().strip()
        if not raw:
            return
        pid = _extract_page_id(raw)
        for r in range(pages_table.rowCount()):
            if pages_table.item(r, 0) and pages_table.item(r, 0).text() == pid:
                page_input.clear()
                return
        row = pages_table.rowCount()
        pages_table.insertRow(row)
        pages_table.setItem(row, 0, QTableWidgetItem(pid))
        _set_page_status_item(pages_table, row, pid, _per_page_on_open)
        page_input.clear()

    add_page_btn.clicked.connect(_add_page_row)
    page_input.returnPressed.connect(_add_page_row)
    ctrl_row.addWidget(add_page_btn)

    del_page_btn = QPushButton("Delete Item")
    del_page_btn.setStyleSheet(_BTN_RED)

    def _del_page_row():
        rows = sorted(
            {idx.row() for idx in pages_table.selectedIndexes()},
            reverse=True,
        )
        for r in rows:
            pages_table.removeRow(r)

    del_page_btn.clicked.connect(_del_page_row)
    ctrl_row.addWidget(del_page_btn)

    ctrl_row.addWidget(_help_btn(dlg, _PAGEID_HELP_HTML))

    pages_vbox.addLayout(ctrl_row)

    creds_form.addRow("Page IDs / URLs:", pages_outer)

    # Deck root row
    deck_container = QWidget()
    deck_row = QHBoxLayout(deck_container)
    deck_row.setContentsMargins(0, 0, 0, 0)

    deck_root_edit = QLineEdit(config.get("deck_root", ""))
    deck_root_edit.setPlaceholderText("e.g. Notion  (blank = top-level decks)")
    deck_row.addWidget(deck_root_edit)
    deck_row.addWidget(_help_btn(dlg, _DECK_HELP_HTML))

    creds_form.addRow("Deck root:", deck_container)

    # Formatting guide button
    fmt_btn = QPushButton("  Formatting Guide  —  how to structure your Notion page  →")
    fmt_btn.setStyleSheet(_BTN_TEAL)
    fmt_btn.setToolTip("Learn how to format toggle Q&A, cloze, and table cards")

    def _show_format_guide():
        try:
            from aqt.qt import QDialog, QVBoxLayout, QTextBrowser, QPushButton as Btn  # type: ignore
        except ImportError:
            return
        d = QDialog(dlg)
        d.setWindowTitle("Notion Page Formatting Guide")
        d.setMinimumSize(600, 560)
        lay = QVBoxLayout(d)
        browser = QTextBrowser()
        browser.setHtml(_FORMAT_GUIDE_HTML)
        browser.setOpenExternalLinks(True)
        lay.addWidget(browser)
        close = Btn("Close")
        close.setStyleSheet(_BTN_GREY)
        close.clicked.connect(d.accept)
        lay.addWidget(close)
        d.exec()

    fmt_btn.clicked.connect(_show_format_guide)
    creds_form.addRow("", fmt_btn)

    root.addWidget(creds)

    # ---- Auto-sync ----
    sync_grp = QGroupBox("Auto-sync")
    sync_grp.setStyleSheet("QGroupBox{font-weight:bold;font-size:12px;}")
    sync_form = QFormLayout(sync_grp)
    sync_form.setVerticalSpacing(8)

    auto_check = QCheckBox()
    auto_check.setChecked(config.get("auto_sync_enabled", False))
    sync_form.addRow("Enable auto-sync:", auto_check)

    interval_combo = QComboBox()
    _saved_minutes = config.get("auto_sync_interval_minutes", 15)
    _closest_idx = 0
    for _i, (_label, _mins) in enumerate(_SYNC_INTERVALS):
        interval_combo.addItem(_label, _mins)
        if _mins == _saved_minutes:
            _closest_idx = _i
    interval_combo.setCurrentIndex(_closest_idx)
    sync_form.addRow("Sync every:", interval_combo)

    # Last sync status row
    _status_text, _status_color = _status_display(_load_sync_status())
    status_lbl = QLabel(_status_text)
    status_lbl.setStyleSheet(
        f"color:{_status_color};font-size:11px;padding:4px 6px;"
        "background:#F8F9FA;border-radius:3px;border:1px solid #E5E7E9;"
    )
    status_lbl.setWordWrap(True)
    sync_form.addRow("Last sync:", status_lbl)

    root.addWidget(sync_grp)

    # ---- Refresh callback — updates both status label and table column after sync ----
    def _refresh_ui() -> None:
        if not dlg.isVisible():
            return
        s = _load_sync_status()
        t, c = _status_display(s)
        status_lbl.setText(t)
        status_lbl.setStyleSheet(
            f"color:{c};font-size:11px;padding:4px 6px;"
            "background:#F8F9FA;border-radius:3px;border:1px solid #E5E7E9;"
        )
        pp = (s or {}).get("per_page", {})
        for r in range(pages_table.rowCount()):
            pid_item = pages_table.item(r, 0)
            if pid_item:
                _set_page_status_item(pages_table, r, pid_item.text(), pp)

    # ---- Button row ----
    btn_row = QHBoxLayout()

    sync_now_btn = QPushButton("Sync Now")
    sync_now_btn.setStyleSheet(_BTN_BLUE)
    sync_now_btn.setToolTip("Run a sync immediately with the current (unsaved) settings")
    sync_now_btn.clicked.connect(lambda: _save_and_act(
        dlg, token_edit, pages_table, deck_root_edit,
        auto_check, interval_combo, config, sync_now=True, on_complete=_refresh_ui
    ))
    btn_row.addWidget(sync_now_btn)

    btn_row.addStretch()

    cancel_btn = QPushButton("Cancel")
    cancel_btn.setStyleSheet(_BTN_RED)
    cancel_btn.clicked.connect(dlg.reject)
    btn_row.addWidget(cancel_btn)

    save_btn = QPushButton("Save & Auto-sync")
    save_btn.setStyleSheet(_BTN_GREEN)
    save_btn.setToolTip("Save settings and start/restart the auto-sync timer")
    save_btn.clicked.connect(lambda: _save_and_act(
        dlg, token_edit, pages_table, deck_root_edit,
        auto_check, interval_combo, config, sync_now=False, on_complete=None
    ))
    btn_row.addWidget(save_btn)

    root.addLayout(btn_row)

    dlg.exec()


# ---------------------------------------------------------------------------
# Save + dispatch helper
# ---------------------------------------------------------------------------

def _save_and_act(dlg, token_edit, pages_table, deck_root_edit,
                  auto_check, interval_combo, old_config, *, sync_now: bool,
                  on_complete=None) -> None:
    """Validate, persist config, then optionally kick off a sync."""
    try:
        from aqt import mw  # type: ignore
        from aqt.qt import QMessageBox  # type: ignore
    except ImportError:
        return

    token = token_edit.text().strip()
    if not token:
        QMessageBox.warning(dlg, "Missing token",
                            "Please enter your Notion integration token before saving.")
        return

    page_ids = [
        pages_table.item(r, 0).text()
        for r in range(pages_table.rowCount())
        if pages_table.item(r, 0)
    ]

    new_config = {
        "notion_token": token,
        "page_ids": page_ids,
        "auto_sync_enabled": auto_check.isChecked(),
        "auto_sync_interval_minutes": interval_combo.currentData(),
        "deck_root": deck_root_edit.text().strip(),
        "on_source_deleted": old_config.get("on_source_deleted", "ignore"),
    }
    mw.addonManager.writeConfig(_ADDON_NAME, new_config)
    _restart_autosync_timer(new_config)

    if sync_now:
        on_sync_now_clicked(parent=dlg, on_complete=on_complete)
    else:
        dlg.accept()


def _extract_page_id(value: str) -> str:
    """Accept a bare ID, UUID, or full Notion URL; return just the 32-char hex ID."""
    import re

    _32HEX = r"[0-9a-f]{32}"
    _UUID  = r"([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})"

    # Strip query string and fragment
    value = value.split("?")[0].split("#")[0].rstrip("/")

    # Bare 32-char hex (no dashes)
    if re.fullmatch(_32HEX, value, re.IGNORECASE):
        return value.lower()

    # UUID format a1b2c3d4-e5f6-7890-a1b2-c3d4e5f67890
    m = re.fullmatch(_UUID, value, re.IGNORECASE)
    if m:
        return "".join(m.groups()).lower()

    # URL — grab the last path segment
    segment = value.split("/")[-1]

    if re.fullmatch(_32HEX, segment, re.IGNORECASE):
        return segment.lower()

    m = re.search(_UUID, segment, re.IGNORECASE)
    if m:
        return "".join(m.groups()).lower()

    # Notion URL slug format: "Page-Title-{32hexchars}" — ID is always after the last dash
    last_part = segment.split("-")[-1]
    if re.fullmatch(_32HEX, last_part, re.IGNORECASE):
        return last_part.lower()

    return value  # unrecognised — pass through as-is


# ---------------------------------------------------------------------------
# Sync-now handler
# ---------------------------------------------------------------------------

def on_sync_now_clicked(parent=None, on_complete=None) -> None:
    """Run a sync in the background, showing a live progress dialog, then a summary."""
    try:
        from aqt import mw  # type: ignore
        from aqt.utils import showInfo, showCritical  # type: ignore
        from aqt.operations import QueryOp  # type: ignore
    except ImportError:
        raise RuntimeError("aqt not available")

    from .sync import run_sync

    def _progress_cb(msg: str) -> None:
        """Called from the background thread — post label update to the main thread."""
        try:
            mw.taskman.run_on_main(
                lambda: mw.progress.update(label=f"Notion → Anki\n\n{msg}")
            )
        except Exception:
            pass

    def _background(_col) -> object:
        cfg = mw.addonManager.getConfig(_ADDON_NAME) or {}
        return run_sync(col=mw.col, config=cfg, progress_cb=_progress_cb)

    def _on_success(result) -> None:
        _save_sync_status(
            success=True,
            added=result.added, updated=result.updated,
            skipped=result.skipped, errors=result.errors,
            per_page_results=result.per_page_results,
        )
        if on_complete:
            try:
                on_complete()
            except Exception:
                pass
        total = result.added + result.updated
        msg = f"Sync complete!\n\n{total} card{'s' if total != 1 else ''} synced  ·  {result.added} new  ·  {result.updated} updated"
        if result.errors:
            msg += f"\n\n{len(result.errors)} error(s):\n" + "\n".join(result.errors[:5])
        showInfo(msg, parent=parent, title="NotionSync for Anki")

    def _on_failure(exc: Exception) -> None:
        _save_sync_status(success=False, error_msg=str(exc))
        if on_complete:
            try:
                on_complete()
            except Exception:
                pass
        showCritical(str(exc), parent=parent, title="NotionSync for Anki — Error")

    (
        QueryOp(parent=mw, op=_background, success=_on_success)
        .failure(_on_failure)
        .with_progress("Notion → Anki: starting sync…")
        .run_in_background()
    )


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
