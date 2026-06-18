"""Unit tests for convert.toggles — offline, no Anki required."""
import json
import os
import pytest

from notion_to_anki.convert.toggles import (
    Card,
    collect_top_level_toggles,
    toggle_to_card,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class TestCollectTopLevelToggles:
    def test_filters_non_toggle(self):
        blocks = _load("blocks_simple.json")
        toggles = collect_top_level_toggles(blocks)
        assert len(toggles) == 1
        assert toggles[0]["id"] == "block-001"

    def test_empty_list(self):
        assert collect_top_level_toggles([]) == []

    def test_all_toggles(self):
        blocks = _load("blocks_nested.json")
        # top-level only
        assert len(collect_top_level_toggles(blocks)) == 1


class TestToggleToCard:
    def test_simple_toggle(self):
        blocks = _load("blocks_simple.json")
        toggle = collect_top_level_toggles(blocks)[0]
        card = toggle_to_card(toggle)

        assert isinstance(card, Card)
        assert "What is mitosis?" in card.front
        assert "Cell division" in card.back
        assert card.extra == ""
        assert card.notion_block_id == "block-001"

    def test_nested_toggle_goes_to_extra(self):
        blocks = _load("blocks_nested.json")
        toggle = collect_top_level_toggles(blocks)[0]
        card = toggle_to_card(toggle)

        assert "What are the phases" in card.front
        # The paragraph child goes to back
        assert "There are four main phases" in card.back
        # The nested toggle goes to extra as <details>
        assert "<details>" in card.extra
        assert "prophase" in card.extra
        assert "Chromatin condenses" in card.extra

    def test_rich_formatting(self):
        blocks = _load("blocks_rich.json")
        toggle = collect_top_level_toggles(blocks)[0]
        card = toggle_to_card(toggle)

        assert "<b>Bold</b>" in card.back
        assert "<i>italic</i>" in card.back
        assert "<code>code</code>" in card.back
        assert 'notion-red' in card.back
        assert 'notion-yellow_background' in card.back
        # block equation
        assert "\\[E = mc^2\\]" in card.back

    def test_card_block_id(self):
        blocks = _load("blocks_simple.json")
        toggle = collect_top_level_toggles(blocks)[0]
        card = toggle_to_card(toggle)
        assert card.notion_block_id == "block-001"
