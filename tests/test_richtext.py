"""Unit tests for convert.richtext — offline, no Anki required."""
import pytest
from notion_to_anki.convert.richtext import rich_text_to_html, block_to_html, _render_children


def _text(content, **annotations):
    ann = {
        "bold": False, "italic": False, "strikethrough": False,
        "underline": False, "code": False, "color": "default",
    }
    ann.update(annotations)
    return {"type": "text", "text": {"content": content, "link": None}, "annotations": ann}


def _equation_inline(expr):
    return {"type": "equation", "equation": {"expression": expr}}


class TestRichTextToHtml:
    def test_plain(self):
        assert rich_text_to_html([_text("hello")]) == "hello"

    def test_bold(self):
        assert rich_text_to_html([_text("x", bold=True)]) == "<b>x</b>"

    def test_italic(self):
        assert rich_text_to_html([_text("x", italic=True)]) == "<i>x</i>"

    def test_strikethrough(self):
        assert rich_text_to_html([_text("x", strikethrough=True)]) == "<s>x</s>"

    def test_underline(self):
        assert rich_text_to_html([_text("x", underline=True)]) == "<u>x</u>"

    def test_code(self):
        assert rich_text_to_html([_text("x", code=True)]) == "<code>x</code>"

    def test_color(self):
        html = rich_text_to_html([_text("x", color="red")])
        assert 'class="notion-red"' in html
        assert "x" in html

    def test_background_color(self):
        html = rich_text_to_html([_text("x", color="yellow_background")])
        assert 'class="notion-yellow_background"' in html

    def test_link(self):
        item = {
            "type": "text",
            "text": {"content": "click", "link": {"url": "https://example.com"}},
            "annotations": {"bold": False, "italic": False, "strikethrough": False,
                            "underline": False, "code": False, "color": "default"},
        }
        html = rich_text_to_html([item])
        assert '<a href="https://example.com">click</a>' == html

    def test_inline_equation(self):
        html = rich_text_to_html([_equation_inline("E=mc^2")])
        assert "\\(E=mc^2\\)" == html

    def test_html_escaping(self):
        html = rich_text_to_html([_text("<b>not bold</b>")])
        assert "&lt;b&gt;" in html

    def test_multiple_items(self):
        html = rich_text_to_html([_text("A"), _text("B", bold=True)])
        assert html == "A<b>B</b>"


class TestBlockToHtml:
    def test_paragraph(self):
        block = {"type": "paragraph", "paragraph": {"rich_text": [_text("hello")]}}
        assert block_to_html(block) == "<p>hello</p>"

    def test_heading_1(self):
        block = {"type": "heading_1", "heading_1": {"rich_text": [_text("Title")]}}
        assert block_to_html(block) == "<h1>Title</h1>"

    def test_heading_2(self):
        block = {"type": "heading_2", "heading_2": {"rich_text": [_text("Sub")]}}
        assert block_to_html(block) == "<h2>Sub</h2>"

    def test_equation_block(self):
        block = {"type": "equation", "equation": {"expression": "x^2"}}
        assert block_to_html(block) == "\\[x^2\\]"

    def test_divider(self):
        block = {"type": "divider", "divider": {}}
        assert block_to_html(block) == "<hr>"

    def test_quote(self):
        block = {"type": "quote", "quote": {"rich_text": [_text("wise words")]}}
        assert "<blockquote>" in block_to_html(block)

    def test_code_block(self):
        block = {
            "type": "code",
            "code": {"language": "python", "rich_text": [_text("print('hi')")]},
        }
        html = block_to_html(block)
        assert "<pre>" in html
        assert 'language-python' in html

    def test_toggle_nested(self):
        block = {
            "type": "toggle",
            "toggle": {"rich_text": [_text("Q")]},
            "children": [
                {"type": "paragraph", "paragraph": {"rich_text": [_text("A")]}}
            ],
        }
        html = block_to_html(block)
        assert "<details>" in html
        assert "<summary>Q</summary>" in html
        assert "A" in html


class TestRenderChildren:
    def test_wraps_list_items_ul(self):
        blocks = [
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_text("A")]}},
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_text("B")]}},
        ]
        html = _render_children(blocks)
        assert html.startswith("<ul>")
        assert html.endswith("</ul>")
        assert "<li>A</li>" in html

    def test_wraps_list_items_ol(self):
        blocks = [
            {"type": "numbered_list_item", "numbered_list_item": {"rich_text": [_text("1st")]}},
        ]
        html = _render_children(blocks)
        assert "<ol>" in html
        assert "</ol>" in html

    def test_mixed_blocks(self):
        blocks = [
            {"type": "paragraph", "paragraph": {"rich_text": [_text("intro")]}},
            {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_text("item")]}},
            {"type": "paragraph", "paragraph": {"rich_text": [_text("outro")]}},
        ]
        html = _render_children(blocks)
        assert "<p>intro</p>" in html
        assert "<ul>" in html
        assert "<p>outro</p>" in html
