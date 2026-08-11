"""Regression tests for the cross-machine failures found in the crash report.

Each test pins one previously-broken behaviour:
  * sub-pages were downloaded once per ancestor (9 pages -> 99 API calls)
  * a torn id-map file failed every future sync permanently
  * the id-map was rewritten once per card, non-atomically
  * cancellation only landed at card boundaries, never during downloads
  * cancelling threw away the ids of cards already added -> duplicates on rerun
"""
import json
import os
import threading

import pytest

from notion_to_anki.notion.blocks import fetch_block_tree
from notion_to_anki.notion.client import NotionClient
import notion_to_anki.anki_io.writer as writer
from notion_to_anki import sync as sync_mod


# ---------------------------------------------------------------------------
# fetch_block_tree must not descend into sub-pages / sub-databases
# ---------------------------------------------------------------------------

class RecordingClient:
    def __init__(self, tree):
        self.tree = tree
        self.calls = []

    def get_block_children(self, block_id):
        self.calls.append(block_id)
        return json.loads(json.dumps(self.tree.get(block_id, [])))


def _blk(bid, btype, has_children=False):
    return {"id": bid, "type": btype, "has_children": has_children,
            btype: {"rich_text": []}}


class TestFetchBlockTreeStopsAtSubPages:
    def test_does_not_expand_child_page(self):
        client = RecordingClient({
            "root": [_blk("sub", "child_page", True)],
            "sub": [_blk("deep", "paragraph")],
        })
        tree = fetch_block_tree(client, "root")

        assert "children" not in tree[0], "child_page must be left for run_sync"
        assert client.calls == ["root"]

    def test_does_not_expand_child_database(self):
        client = RecordingClient({
            "root": [_blk("db", "child_database", True)],
            "db": [_blk("deep", "paragraph")],
        })
        fetch_block_tree(client, "root")
        assert client.calls == ["root"]

    def test_still_expands_normal_blocks(self):
        client = RecordingClient({
            "root": [_blk("tog", "toggle", True)],
            "tog": [_blk("ans", "paragraph")],
        })
        tree = fetch_block_tree(client, "root")
        assert tree[0]["children"][0]["id"] == "ans"


# ---------------------------------------------------------------------------
# id-map: corruption tolerance and atomic writes
# ---------------------------------------------------------------------------

@pytest.fixture
def map_file(tmp_path, monkeypatch):
    path = tmp_path / "notion_block_id_map.json"
    monkeypatch.setattr(writer, "_map_path", lambda: str(path))
    return path


class TestIdMap:
    def test_missing_file_is_empty(self, map_file):
        assert writer.load_id_map() == {}

    def test_truncated_file_does_not_raise(self, map_file):
        map_file.write_text('{\n  "abc": "1699', encoding="utf-8")
        assert writer.load_id_map() == {}

    def test_non_dict_json_does_not_raise(self, map_file):
        map_file.write_text("[1, 2, 3]", encoding="utf-8")
        assert writer.load_id_map() == {}

    def test_round_trip(self, map_file):
        writer.save_id_map({"a": "1"})
        assert writer.load_id_map() == {"a": "1"}

    def test_save_is_atomic(self, map_file):
        """A failure mid-write must leave the previous file intact."""
        writer.save_id_map({"good": "1"})

        real_dump = json.dump

        def exploding_dump(obj, fh, **kw):
            real_dump(obj, fh, **kw)
            raise OSError("disk full")

        json.dump = exploding_dump
        try:
            with pytest.raises(OSError):
                writer.save_id_map({"bad": "2"})
        finally:
            json.dump = real_dump

        # the half-written data went to the .tmp file; the real one is untouched
        assert writer.load_id_map() == {"good": "1"}


# ---------------------------------------------------------------------------
# Cancellation reaches into the network layer
# ---------------------------------------------------------------------------

class TestClientCancellation:
    def test_check_cancel_runs_before_request(self):
        """The hook must fire before any socket work, so a cancelled run stops
        at the next request rather than after the whole page tree downloads."""
        class Boom(Exception):
            pass

        def check():
            raise Boom()

        client = NotionClient("tok", check_cancel=check)
        with pytest.raises(Boom):
            client.get_page("abc")          # never touches the network

    def test_backoff_sleep_is_interruptible(self):
        """A 429 back-off must not hold a cancel hostage for its full duration."""
        calls = []

        class Boom(Exception):
            pass

        def check():
            calls.append(1)
            if len(calls) > 2:
                raise Boom()

        client = NotionClient("tok", check_cancel=check)
        with pytest.raises(Boom):
            client._sleep(30.0)             # would block 30s without the hook
        assert len(calls) <= 5

    def test_no_hook_means_no_behaviour_change(self):
        client = NotionClient("tok")
        client._cancel_point()              # must be a no-op


# ---------------------------------------------------------------------------
# run_sync: cancellation persists what was already imported
# ---------------------------------------------------------------------------

class FakeCol:
    """Minimal stand-in for an Anki collection."""
    def __init__(self):
        self.notes = []

    class _Models:
        def by_name(self, n):
            return {"flds": [{"name": "Front"}, {"name": "Back"},
                             {"name": "Extra"}, {"name": "NotionBlockId"}],
                    "name": n}

    class _Decks:
        def id(self, name):
            return 1

    models = _Models()
    decks = _Decks()

    def new_note(self, model):
        col = self

        class N(dict):
            id = len(col.notes) + 1000
            def __setitem__(self, k, v):
                dict.__setitem__(self, k, v)
        return N()

    def add_note(self, note, deck_id):
        self.notes.append(note)


def _page_tree(n_cards):
    children = [
        {"id": f"tog{i}", "type": "toggle", "has_children": False,
         "toggle": {"rich_text": [{"plain_text": f"Q{i}", "annotations": {},
                                   "type": "text", "text": {"content": f"Q{i}"}}]}}
        for i in range(n_cards)
    ]
    return children


class TestRunSyncCancellation:
    def test_partial_ids_are_persisted(self, map_file, monkeypatch):
        """Stopping mid-import must still save the ids of cards already created,
        otherwise the next run re-adds every one of them as a duplicate."""
        cancel = threading.Event()
        page = "a" * 32

        class Client:
            def __init__(self, token, check_cancel=None):
                self.check_cancel = check_cancel
            def get_page(self, pid):
                return {"object": "page", "properties": {
                    "N": {"type": "title", "title": [{"plain_text": "P"}]}}}
            def get_database(self, d):
                raise AssertionError("should not be reached")
            def get_block_children(self, bid):
                return _page_tree(5)

        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient", Client)

        col = FakeCol()
        # cancel after the 3rd progress report mentioning a card
        seen = {"n": 0}

        def progress(msg):
            if "Card " in msg:
                seen["n"] += 1
                if seen["n"] == 3:
                    cancel.set()

        with pytest.raises(sync_mod.SyncCancelledError):
            sync_mod.run_sync(page_ids=[page], col=col,
                              config={"notion_token": "t", "page_ids": [page]},
                              progress_cb=progress, cancel_event=cancel)

        saved = writer.load_id_map()
        assert saved, "id map must be written on cancellation"
        assert len(saved) == len(col.notes), \
            "every note added to the collection must be in the saved map"

    def test_cancel_before_start_adds_nothing(self, map_file, monkeypatch):
        cancel = threading.Event()
        cancel.set()
        page = "a" * 32

        class Client:
            def __init__(self, token, check_cancel=None):
                pass
            def get_page(self, pid):
                raise AssertionError("cancelled run must not hit the network")
            def get_database(self, d):
                raise AssertionError("cancelled run must not hit the network")
            def get_block_children(self, bid):
                raise AssertionError("cancelled run must not hit the network")

        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient", Client)

        col = FakeCol()
        with pytest.raises(sync_mod.SyncCancelledError):
            sync_mod.run_sync(page_ids=[page], col=col,
                              config={"notion_token": "t", "page_ids": [page]},
                              cancel_event=cancel)
        assert col.notes == []


# ---------------------------------------------------------------------------
# writer no longer does per-card file I/O
# ---------------------------------------------------------------------------

class TestMediaUrlSubstitution:
    """The renderer HTML-escapes '&' into the img src, so the raw Notion URL
    never matched and every image kept an S3 link that expires within the hour."""

    def _toggle_with_image(self, url):
        return {
            "id": "tog1", "type": "toggle", "has_children": True,
            "toggle": {"rich_text": []},
            "children": [{"id": "img1", "type": "image", "has_children": False,
                          "image": {"file": {"url": url}}}],
        }

    def test_signed_url_with_ampersands_is_replaced(self):
        from notion_to_anki.convert.toggles import toggle_to_card

        url = ("https://prod-files-secure.s3.us-west-2.amazonaws.com/x/y/image.png"
               "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=abc&X-Amz-Signature=def")
        block = self._toggle_with_image(url)
        card = toggle_to_card(block)
        assert "&amp;" in card.back, "precondition: renderer escapes the URL"

        card = sync_mod._process_media(
            card, block, col=None,
            ingest_image=lambda col, u: "notion_deadbeef.png",
            image_block_url=lambda b: b["image"]["file"]["url"],
            ingest_audio=lambda col, u: "x.mp3",
            audio_block_url=lambda b: None,
        )

        assert 'src="notion_deadbeef.png"' in card.back
        assert "amazonaws.com" not in card.back
        assert "X-Amz" not in card.back

    def test_plain_url_still_replaced(self):
        from notion_to_anki.convert.toggles import toggle_to_card

        url = "https://example.com/pic.png"
        block = self._toggle_with_image(url)
        card = toggle_to_card(block)
        card = sync_mod._process_media(
            card, block, col=None,
            ingest_image=lambda col, u: "notion_cafe.png",
            image_block_url=lambda b: b["image"]["file"]["url"],
            ingest_audio=lambda col, u: "x.mp3",
            audio_block_url=lambda b: None,
        )
        assert 'src="notion_cafe.png"' in card.back

    def test_download_failure_is_reported_not_swallowed(self):
        from notion_to_anki.convert.toggles import toggle_to_card

        block = self._toggle_with_image("https://example.com/a.png?x=1&y=2")
        card = toggle_to_card(block)
        errors = []

        def boom(col, url):
            raise RuntimeError("HTTP 403")

        sync_mod._process_media(
            card, block, col=None,
            ingest_image=boom,
            image_block_url=lambda b: b["image"]["file"]["url"],
            ingest_audio=lambda col, u: "x.mp3",
            audio_block_url=lambda b: None,
            errors=errors,
        )
        assert len(errors) == 1
        assert "HTTP 403" in errors[0]


class TestIndexExistingNotes:
    """A lost id-map cache must be rebuilt from the collection, not cause
    every card to be re-added as a duplicate."""

    class Col:
        def __init__(self, mapping):
            self._m = mapping
        def find_notes(self, query):
            assert "NotionBlockId" in query
            return list(self._m)
        def get_note(self, nid):
            return {"NotionBlockId": self._m[nid]}

    def test_rebuilds_map_from_notes(self):
        col = self.Col({101: "blk-a", 102: "blk-b"})
        assert writer.index_existing_notes(col) == {"blk-a": "101", "blk-b": "102"}

    def test_skips_blank_block_ids(self):
        col = self.Col({101: "  ", 102: "blk-b"})
        assert writer.index_existing_notes(col) == {"blk-b": "102"}

    def test_search_failure_is_not_fatal(self):
        class Broken:
            def find_notes(self, q):
                raise RuntimeError("no such field")
        assert writer.index_existing_notes(Broken()) == {}


class TestWriterDoesNoFileIO:
    def test_upsert_does_not_touch_disk(self, map_file):
        from notion_to_anki.convert.toggles import Card

        col = FakeCol()
        id_map = {}
        model = col.models.by_name("m")
        for i in range(5):
            writer.upsert_card(col, Card(f"F{i}", "B", "", f"blk{i}"),
                               1, model, id_map)

        assert len(id_map) == 5
        assert not map_file.exists(), \
            "upsert_card must not write the map; the caller persists it once"
