"""Notion rich_text / block content → HTML, preserving formatting.

Handles:
  * annotations: bold, italic, strikethrough, underline, code, color/background
    (mapped to <b>/<i>/<s>/<u>/<code> and CSS classes for colors).
  * links (text.link.url).
  * inline equations (rich_text item type "equation") → MathJax \\( ... \\).
  * block-level equation blocks → MathJax \\[ ... \\].

Colors map to CSS classes (e.g. notion-red, notion-blue_background) defined in the
note type's bundled CSS so they render the same as in Notion.
"""
from __future__ import annotations

_COLOR_CLASS = {
    "gray": "notion-gray",
    "brown": "notion-brown",
    "orange": "notion-orange",
    "yellow": "notion-yellow",
    "green": "notion-green",
    "blue": "notion-blue",
    "purple": "notion-purple",
    "pink": "notion-pink",
    "red": "notion-red",
    "gray_background": "notion-gray_background",
    "brown_background": "notion-brown_background",
    "orange_background": "notion-orange_background",
    "yellow_background": "notion-yellow_background",
    "green_background": "notion-green_background",
    "blue_background": "notion-blue_background",
    "purple_background": "notion-purple_background",
    "pink_background": "notion-pink_background",
    "red_background": "notion-red_background",
}


def rich_text_to_html(rich_text: list[dict]) -> str:
    """Convert a Notion rich_text array into an HTML string with formatting preserved."""
    parts = []
    for item in rich_text:
        item_type = item.get("type", "text")

        if item_type == "equation":
            expr = item.get("equation", {}).get("expression", "")
            parts.append(f"\\({_escape(expr)}\\)")
            continue

        if item_type == "mention":
            # render plain text of the mention
            plain = item.get("plain_text", "")
            parts.append(_escape(plain))
            continue

        # default: text item
        plain = item.get("text", {}).get("content", "")
        link_info = item.get("text", {}).get("link")
        link_url = link_info.get("url", "") if isinstance(link_info, dict) else ""

        html = _escape(plain)

        ann = item.get("annotations", {})
        if ann.get("code"):
            html = f"<code>{html}</code>"
        if ann.get("bold"):
            html = f"<b>{html}</b>"
        if ann.get("italic"):
            html = f"<i>{html}</i>"
        if ann.get("strikethrough"):
            html = f"<s>{html}</s>"
        if ann.get("underline"):
            html = f"<u>{html}</u>"

        color = ann.get("color", "default")
        if color and color != "default":
            css_class = _COLOR_CLASS.get(color, f"notion-{color}")
            html = f'<span class="{css_class}">{html}</span>'

        if link_url:
            html = f'<a href="{_escape_attr(link_url)}">{html}</a>'

        parts.append(html)
    return "".join(parts)


def block_to_html(block: dict) -> str:
    """Convert a single content block (paragraph, list item, image, equation …) to HTML."""
    btype = block.get("type", "")
    data = block.get(btype, {})

    if btype == "paragraph":
        inner = rich_text_to_html(data.get("rich_text", []))
        return f"<p>{inner}</p>"

    if btype in ("heading_1", "heading_2", "heading_3"):
        level = btype[-1]
        inner = rich_text_to_html(data.get("rich_text", []))
        return f"<h{level}>{inner}</h{level}>"

    if btype == "bulleted_list_item":
        inner = rich_text_to_html(data.get("rich_text", []))
        children = block.get("children", [])
        child_html = _render_children(children) if children else ""
        return f"<li>{inner}{child_html}</li>"

    if btype == "numbered_list_item":
        inner = rich_text_to_html(data.get("rich_text", []))
        children = block.get("children", [])
        child_html = _render_children(children) if children else ""
        return f"<li>{inner}{child_html}</li>"

    if btype == "code":
        lang = data.get("language", "")
        inner = rich_text_to_html(data.get("rich_text", []))
        return f'<pre><code class="language-{_escape_attr(lang)}">{inner}</code></pre>'

    if btype == "equation":
        expr = data.get("expression", "")
        return f"\\[{_escape(expr)}\\]"

    if btype == "divider":
        return "<hr>"

    if btype == "quote":
        inner = rich_text_to_html(data.get("rich_text", []))
        return f"<blockquote>{inner}</blockquote>"

    if btype == "callout":
        icon = data.get("icon", {})
        emoji = icon.get("emoji", "") if isinstance(icon, dict) else ""
        inner = rich_text_to_html(data.get("rich_text", []))
        prefix = f"{emoji} " if emoji else ""
        return f'<div class="notion-callout">{prefix}{inner}</div>'

    if btype == "image":
        # URL substituted later by media.py; emit a placeholder with the raw URL
        img_data = data
        url = ""
        if "file" in img_data:
            url = img_data["file"].get("url", "")
        elif "external" in img_data:
            url = img_data["external"].get("url", "")
        caption = rich_text_to_html(img_data.get("caption", []))
        img_tag = f'<img src="{_escape_attr(url)}">'
        if caption:
            return f'<figure>{img_tag}<figcaption>{caption}</figcaption></figure>'
        return img_tag

    if btype == "toggle":
        # nested toggle in back content → details/summary
        inner_front = rich_text_to_html(data.get("rich_text", []))
        children = block.get("children", [])
        inner_back = _render_children(children)
        return f"<details><summary>{inner_front}</summary>{inner_back}</details>"

    if btype == "audio":
        url = ""
        if "file" in data:
            url = data["file"].get("url", "")
        elif "external" in data:
            url = data["external"].get("url", "")
        if url:
            return f"[sound:{url}]"
        return ""

    if btype == "table":
        children = block.get("children", [])
        has_header = data.get("has_column_header", False)
        rows_html: list[str] = []
        for i, row in enumerate(children):
            if row.get("type") != "table_row":
                continue
            cells = row.get("table_row", {}).get("cells", [])
            tag = "th" if (has_header and i == 0) else "td"
            cells_html = "".join(
                f"<{tag}>{rich_text_to_html(cell)}</{tag}>" for cell in cells
            )
            rows_html.append(f"<tr>{cells_html}</tr>")
        return f'<table border="1" style="border-collapse:collapse">{"".join(rows_html)}</table>'

    if btype == "table_of_contents":
        return ""

    # fallback: extract any rich_text the block may carry
    rt = data.get("rich_text", [])
    if rt:
        return f"<p>{rich_text_to_html(rt)}</p>"
    return ""


def _render_children(blocks: list[dict]) -> str:
    """Render a list of blocks as HTML, wrapping adjacent list items in <ul>/<ol>."""
    parts: list[str] = []
    in_ul = False
    in_ol = False

    for block in blocks:
        btype = block.get("type", "")

        if btype == "bulleted_list_item":
            if in_ol:
                parts.append("</ol>")
                in_ol = False
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
        elif btype == "numbered_list_item":
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            if not in_ol:
                parts.append("<ol>")
                in_ol = True
        else:
            if in_ul:
                parts.append("</ul>")
                in_ul = False
            if in_ol:
                parts.append("</ol>")
                in_ol = False

        parts.append(block_to_html(block))

    if in_ul:
        parts.append("</ul>")
    if in_ol:
        parts.append("</ol>")

    return "".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "&quot;")
