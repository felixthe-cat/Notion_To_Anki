"""Unit tests for notion.blocks — offline, no Anki required."""
import json
import os
import pytest

from notion_to_anki.notion.blocks import get_page_title, fetch_block_tree

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class TestGetPageTitle:
    def test_extracts_title(self):
        page = _load("page_object.json")
        assert get_page_title(page) == "Biology"

    def test_empty_properties(self):
        assert get_page_title({"properties": {}}) == "Untitled"

    def test_missing_properties(self):
        assert get_page_title({}) == "Untitled"


class TestFetchBlockTree:
    def test_attaches_children(self):
        """fetch_block_tree should attach pre-fetched children supplied by the stub client."""

        class StubClient:
            def __init__(self, blocks_map):
                self._map = blocks_map

            def get_block_children(self, block_id):
                return self._map.get(block_id, [])

        parent_block = {
            "id": "parent-1",
            "type": "toggle",
            "has_children": True,
            "toggle": {"rich_text": []},
        }
        child_block = {
            "id": "child-1",
            "type": "paragraph",
            "has_children": False,
            "paragraph": {"rich_text": []},
        }

        client = StubClient({
            "root": [parent_block],
            "parent-1": [child_block],
        })

        tree = fetch_block_tree(client, "root")
        assert len(tree) == 1
        assert "children" in tree[0]
        assert tree[0]["children"][0]["id"] == "child-1"

    def test_no_children_key_when_has_children_false(self):
        class StubClient:
            def get_block_children(self, block_id):
                return [{"id": "b1", "type": "paragraph", "has_children": False, "paragraph": {"rich_text": []}}]

        tree = fetch_block_tree(StubClient(), "root")
        assert "children" not in tree[0]
