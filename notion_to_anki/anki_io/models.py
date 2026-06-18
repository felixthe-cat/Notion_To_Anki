"""The custom note type used for synced cards.

Defines / ensures a model named "Notion Toggle (3-field)" with fields:
  Front, Back, Extra, NotionBlockId

The card template shows Front on the question side, Back + Extra on the answer side,
and bundles CSS that reproduces Notion text/background colors and styles MathJax output.
"""
from __future__ import annotations

MODEL_NAME = "Notion Toggle (3-field)"
FIELDS = ["Front", "Back", "Extra", "NotionBlockId"]

_QFMT = "{{Front}}"

_AFMT = """\
{{FrontSide}}
<hr id="answer">
{{Back}}
{{#Extra}}
<div class="notion-extra">{{Extra}}</div>
{{/Extra}}"""

_CSS = """\
.card {
  font-family: Arial, sans-serif;
  font-size: 16px;
  text-align: left;
  color: black;
  background-color: white;
  padding: 12px;
}
.notion-extra { margin-top: 12px; }
.notion-extra details { margin: 4px 0; }
.notion-extra summary { cursor: pointer; font-style: italic; color: #555; }

/* Notion text colours */
.notion-gray            { color: #9B9A97; }
.notion-brown           { color: #64473A; }
.notion-orange          { color: #D9730D; }
.notion-yellow          { color: #DFAB01; }
.notion-green           { color: #0F7B6C; }
.notion-blue            { color: #0B6E99; }
.notion-purple          { color: #6940A5; }
.notion-pink            { color: #AD1A72; }
.notion-red             { color: #E03E3E; }

/* Notion background colours */
.notion-gray_background   { background-color: #EBECED; }
.notion-brown_background  { background-color: #E9E5E3; }
.notion-orange_background { background-color: #FAEBDD; }
.notion-yellow_background { background-color: #FBF3DB; }
.notion-green_background  { background-color: #DDEDEA; }
.notion-blue_background   { background-color: #DDEBF1; }
.notion-purple_background { background-color: #EAE4F2; }
.notion-pink_background   { background-color: #F4DFEB; }
.notion-red_background    { background-color: #FBE4E4; }

.notion-callout {
  background: #F7F7F7;
  border-left: 3px solid #CCCCCC;
  padding: 8px 12px;
  margin: 8px 0;
  border-radius: 3px;
}

code {
  background: #F2F2F2;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
}
pre code {
  display: block;
  padding: 8px;
  overflow-x: auto;
}
blockquote {
  border-left: 3px solid #CCCCCC;
  margin: 8px 0;
  padding: 4px 12px;
  color: #555;
}"""


def ensure_model(col):
    """Return the note type, creating it (with templates + CSS) if it doesn't exist."""
    existing = col.models.by_name(MODEL_NAME)
    if existing:
        return existing

    model = col.models.new(MODEL_NAME)

    for field_name in FIELDS:
        fld = col.models.new_field(field_name)
        col.models.add_field(model, fld)

    template = col.models.new_template("Card 1")
    template["qfmt"] = _QFMT
    template["afmt"] = _AFMT
    col.models.add_template(model, template)

    model["css"] = _CSS
    col.models.add(model)
    return col.models.by_name(MODEL_NAME)
