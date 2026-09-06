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
    """Redirect both persisted maps into tmp — otherwise run_sync writes the
    media cache into the real add-on's user_files/ during the test run."""
    path = tmp_path / "notion_block_id_map.json"
    monkeypatch.setattr(writer, "_map_path", lambda: str(path))
    monkeypatch.setattr(writer, "_media_map_path",
                        lambda: str(tmp_path / "notion_media_map.json"))
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


def make_client(page_id, blocks, title="P"):
    """Stub Notion client that serves children per block id.

    Returning the same list for every id makes fetch_block_tree recurse forever
    once a block declares has_children.
    """
    tree = {page_id: blocks}

    def register(bs):
        for b in bs:
            kids = b.pop("children", [])
            if kids:
                tree[b["id"]] = kids
                register(kids)
    register(blocks)

    class Client:
        def __init__(self, token, check_cancel=None):
            self.check_cancel = check_cancel
        def get_page(self, pid):
            return {"object": "page", "properties": {
                "N": {"type": "title", "title": [{"plain_text": title}]}}}
        def get_database(self, d):
            raise AssertionError("should not be reached")
        def get_block_children(self, bid):
            if self.check_cancel:
                self.check_cancel()
            return json.loads(json.dumps(tree.get(bid, [])))
    return Client


def _answer(text="A"):
    """A toggle needs a body, or the sync now skips it as answer-less."""
    return {"id": "ans", "type": "paragraph", "has_children": False,
            "paragraph": {"rich_text": [{"plain_text": text, "annotations": {},
                                         "type": "text", "text": {"content": text}}]}}


def _page_tree(n_cards):
    children = [
        {"id": f"tog{i}", "type": "toggle", "has_children": True,
         "children": [_answer()],
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

        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient",
                            make_client(page, _page_tree(5)))

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


class TestContainerAndEmbedBlocks:
    """Blocks that used to render as an empty string, losing their content."""

    def test_column_children_are_not_lost(self):
        from notion_to_anki.convert.richtext import block_to_html
        block = {
            "type": "column_list", "column_list": {},
            "children": [{
                "type": "column", "column": {},
                "children": [{"type": "paragraph", "has_children": False,
                              "paragraph": {"rich_text": [
                                  {"type": "text", "plain_text": "inside a column",
                                   "text": {"content": "inside a column"},
                                   "annotations": {}}]}}],
            }],
        }
        assert "inside a column" in block_to_html(block)

    def test_synced_block_children_are_not_lost(self):
        from notion_to_anki.convert.richtext import block_to_html
        block = {
            "type": "synced_block", "synced_block": {},
            "children": [{"type": "paragraph", "has_children": False,
                          "paragraph": {"rich_text": [
                              {"type": "text", "plain_text": "synced text",
                               "text": {"content": "synced text"},
                               "annotations": {}}]}}],
        }
        assert "synced text" in block_to_html(block)

    @pytest.mark.parametrize("btype,data", [
        ("embed", {"url": "https://example.com/thing"}),
        ("bookmark", {"url": "https://example.com/thing"}),
        ("video", {"external": {"url": "https://example.com/thing"}}),
        ("pdf", {"file": {"url": "https://example.com/thing"}}),
    ])
    def test_unrenderable_media_becomes_a_link(self, btype, data):
        from notion_to_anki.convert.richtext import block_to_html
        html = block_to_html({"type": btype, btype: data})
        assert 'href="https://example.com/thing"' in html

    def test_embed_without_url_renders_nothing(self):
        from notion_to_anki.convert.richtext import block_to_html
        assert block_to_html({"type": "embed", "embed": {}}) == ""


class TestBlankTogglesAreReported:
    def test_blank_titled_toggle_counted_as_skipped(self, map_file, monkeypatch):
        page = "a" * 32
        blocks = [
            {"id": "t1", "type": "toggle", "has_children": False,
             "toggle": {"rich_text": []}},                      # blank -> skipped
            {"id": "t2", "type": "toggle", "has_children": True,
             "children": [_answer()],
             "toggle": {"rich_text": [{"plain_text": "Q", "annotations": {},
                                       "type": "text", "text": {"content": "Q"}}]}},
        ]

        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient",
                            make_client(page, blocks))
        r = sync_mod.run_sync(page_ids=[page], col=FakeCol(),
                              config={"notion_token": "t", "page_ids": [page]})
        assert r.skipped == 1
        assert any("empty title" in w for w in r.warnings)
        assert not r.errors, "a skipped blank toggle is not a failure"
        assert r.added == 1


class TestLazyDeckCreation:
    """701 Notion pages holding 123 cards must not create 701 Anki decks."""

    class RecordingCol(FakeCol):
        def __init__(self):
            super().__init__()
            self.decks_made = []
            outer = self

            class D:
                def id(self, name):
                    outer.decks_made.append(name)
                    return len(outer.decks_made)
            self.decks = D()

    def _run(self, monkeypatch, page_blocks):
        page = "a" * 32

        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient",
                            make_client(page, page_blocks))
        col = self.RecordingCol()
        sync_mod.run_sync(page_ids=[page], col=col,
                          config={"notion_token": "t", "page_ids": [page]})
        return col

    def test_page_with_no_cards_creates_no_deck(self, map_file, monkeypatch):
        col = self._run(monkeypatch, [
            {"id": "p1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": []}}])
        assert col.decks_made == []

    def test_page_with_cards_still_creates_its_deck(self, map_file, monkeypatch):
        col = self._run(monkeypatch, [
            {"id": "t1", "type": "toggle", "has_children": True,
             "children": [_answer()],
             "toggle": {"rich_text": [{"plain_text": "Q", "annotations": {},
                                       "type": "text", "text": {"content": "Q"}}]}}])
        assert col.decks_made == ["P"]

    def test_deck_created_once_not_per_card(self, map_file, monkeypatch):
        col = self._run(monkeypatch, [
            {"id": f"t{i}", "type": "toggle", "has_children": True,
             "children": [_answer()],
             "toggle": {"rich_text": [{"plain_text": f"Q{i}", "annotations": {},
                                       "type": "text", "text": {"content": f"Q{i}"}}]}}
            for i in range(5)])
        assert col.decks_made == ["P"]


class TestStrandedImagesAreCounted:
    """41% of the eMRCS images sit on pages with no toggles, so no card can hold
    them. That is by design, but it must not be silent."""

    def _img(self, i):
        return {"id": f"i{i}", "type": "image", "has_children": False,
                "image": {"file": {"url": f"https://x/{i}.png"}}}

    def _toggle(self, i, children):
        return {"id": f"t{i}", "type": "toggle", "has_children": bool(children),
                "toggle": {"rich_text": [{"plain_text": "Q", "annotations": {},
                                          "type": "text", "text": {"content": "Q"}}]},
                "children": children}

    def _run(self, monkeypatch, blocks):
        page = "a" * 32

        # Serve children per block id, the way the real API does. Returning the
        # whole page for every id makes fetch_block_tree recurse forever.
        tree = {page: blocks}

        def register(bs):
            for b in bs:
                kids = b.pop("children", [])
                if kids:
                    tree[b["id"]] = kids
                    register(kids)
        register(blocks)

        class Client:
            def __init__(self, token, check_cancel=None): pass
            def get_page(self, pid):
                return {"object": "page", "properties": {
                    "N": {"type": "title", "title": [{"plain_text": "P"}]}}}
            def get_database(self, d): raise AssertionError
            def get_block_children(self, bid):
                return json.loads(json.dumps(tree.get(bid, [])))

        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient", Client)
        monkeypatch.setattr(sync_mod, "_process_media", lambda c, *a, **k: c)
        return sync_mod.run_sync(page_ids=[page], col=FakeCol(),
                                 config={"notion_token": "t", "page_ids": [page]})

    def test_loose_images_on_a_page_with_no_cards(self, map_file, monkeypatch):
        r = self._run(monkeypatch, [self._img(1), self._img(2)])
        assert r.ignored_images == 2
        assert r.pages_with_lost_images == 1
        assert r.added == 0

    def test_images_inside_a_toggle_are_not_counted_as_ignored(self, map_file, monkeypatch):
        r = self._run(monkeypatch, [self._toggle(1, [self._img(1), self._img(2)])])
        assert r.ignored_images == 0
        assert r.added == 1

    def test_mixed_page_counts_only_the_loose_one(self, map_file, monkeypatch):
        r = self._run(monkeypatch, [self._toggle(1, [self._img(1)]), self._img(9)])
        assert r.ignored_images == 1
        # the page made a card but still stranded an image, so it counts
        assert r.pages_with_lost_images == 1

    def test_navigation_page_losing_nothing_is_not_counted(self, map_file, monkeypatch):
        """Most of a Notion tree is card-less navigation that loses nothing.
        Counting those made the warning read '83 images on 578 pages'."""
        r = self._run(monkeypatch, [
            {"id": "p1", "type": "paragraph", "has_children": False,
             "paragraph": {"rich_text": []}}])
        assert r.ignored_images == 0
        assert r.pages_with_lost_images == 0

    def test_nested_images_inside_a_toggle_still_reachable(self, map_file, monkeypatch):
        nested = {"id": "b1", "type": "bulleted_list_item", "has_children": True,
                  "bulleted_list_item": {"rich_text": []},
                  "children": [self._img(1)]}
        r = self._run(monkeypatch, [self._toggle(1, [nested])])
        assert r.ignored_images == 0


class TestMediaCache:
    """Media filenames are content hashes, so the name is unknowable without
    downloading. Cache by image block id or every sync re-fetches every image."""

    def _block(self, url="https://x/a.png?sig=1"):
        return {
            "id": "tog1", "type": "toggle", "has_children": True,
            "toggle": {"rich_text": []},
            "children": [{"id": "img1", "type": "image", "has_children": False,
                          "image": {"file": {"url": url}}}],
        }

    class Col:
        def __init__(self, tmpdir):
            self._dir = str(tmpdir)
            class M:
                def dir(inner):
                    return self._dir
            self.media = M()

    def _call(self, col, media_map, downloads, url="https://x/a.png?sig=1"):
        from notion_to_anki.convert.toggles import toggle_to_card
        block = self._block(url)
        card = toggle_to_card(block)

        def ingest(c, u):
            downloads.append(u)
            return "notion_abc123.png"

        return sync_mod._process_media(
            card, block, col,
            ingest_image=ingest,
            image_block_url=lambda b: b["image"]["file"]["url"],
            ingest_audio=lambda c, u: "x.mp3",
            audio_block_url=lambda b: None,
            media_map=media_map,
        )

    def test_first_sync_downloads_and_records(self, tmp_path):
        col = self.Col(tmp_path)
        mm, dl = {}, []
        card = self._call(col, mm, dl)
        assert dl == ["https://x/a.png?sig=1"]
        assert mm == {"img1": "notion_abc123.png"}
        assert 'src="notion_abc123.png"' in card.back

    def test_second_sync_skips_the_download(self, tmp_path):
        col = self.Col(tmp_path)
        (tmp_path / "notion_abc123.png").write_bytes(b"x")
        mm, dl = {"img1": "notion_abc123.png"}, []
        # a fresh signed URL, as Notion issues on every fetch
        card = self._call(col, mm, dl, url="https://x/a.png?sig=DIFFERENT")
        assert dl == [], "cached image must not be re-downloaded"
        assert 'src="notion_abc123.png"' in card.back

    def test_cache_miss_when_file_was_deleted_from_media(self, tmp_path):
        col = self.Col(tmp_path)  # file absent on disk
        mm, dl = {"img1": "notion_abc123.png"}, []
        self._call(col, mm, dl)
        assert dl, "must re-download if the media file is gone"

    def test_media_map_survives_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(writer, "_media_map_path",
                            lambda: str(tmp_path / "media.json"))
        writer.save_media_map({"img1": "notion_abc.png"})
        assert writer.load_media_map() == {"img1": "notion_abc.png"}

    def test_corrupt_media_map_is_not_fatal(self, tmp_path, monkeypatch):
        p = tmp_path / "media.json"
        p.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(writer, "_media_map_path", lambda: str(p))
        assert writer.load_media_map() == {}


class TestFriendlyNotionErrors:
    """A new user's first failure is almost always a mistyped token or a page
    they forgot to share. Showing Notion's raw JSON told them nothing."""

    def _err(self, status, code, message="raw detail"):
        import json as _json
        from notion_to_anki.notion.client import _friendly_error
        return _friendly_error(status, _json.dumps(
            {"object": "error", "status": status, "code": code, "message": message}))

    def test_bad_token_explains_where_to_get_one(self):
        e = self._err(401, "unauthorized", "API token is invalid.")
        assert "notion.so/profile/integrations" in str(e)
        assert "{" not in str(e), "must not leak raw JSON"
        assert e.status == 401 and e.code == "unauthorized"

    def test_unshared_page_explains_connections(self):
        e = self._err(404, "object_not_found")
        assert "Connections" in str(e)
        assert "{" not in str(e)

    def test_unknown_code_falls_back_to_notion_message(self):
        e = self._err(400, "some_new_code", "Something specific happened.")
        assert str(e) == "Something specific happened."

    def test_unparseable_body_still_gives_a_sentence(self):
        from notion_to_anki.notion.client import _friendly_error
        e = _friendly_error(500, "<html>gateway error</html>")
        assert "HTTP 500" in str(e)

    def test_messages_are_ascii_only(self):
        """These can be written to logs on systems whose encoding is not UTF-8."""
        from notion_to_anki.notion.client import _FRIENDLY
        for v in _FRIENDLY.values():
            assert all(ord(c) < 128 for c in v), v


class TestResolveReportsThePageError:
    """Users paste pages far more often than databases; reporting the database
    attempt told them their page was a 'missing database'."""

    def test_page_error_wins_over_database_error(self):
        from notion_to_anki.notion.client import NotionError

        class C:
            def get_page(self, i):
                raise NotionError("page problem", 404, "object_not_found")
            def get_database(self, i):
                raise NotionError("database problem", 404, "object_not_found")

        with pytest.raises(NotionError) as ei:
            sync_mod._resolve_type_and_title(C(), "x", lambda o: "", lambda o: "")
        assert "page problem" in str(ei.value)

    def test_real_database_still_resolves(self):
        from notion_to_anki.notion.client import NotionError

        class C:
            def get_page(self, i):
                raise NotionError("not a page", 404, "object_not_found")
            def get_database(self, i):
                return {"object": "database"}

        kind, title = sync_mod._resolve_type_and_title(
            C(), "x", lambda o: "P", lambda o: "DB")
        assert (kind, title) == ("database", "DB")


class TestCancelOnAnkiClose:
    """A big Notion tree takes minutes, so quitting Anki mid-sync is normal.
    The background thread must be told to stop before the collection closes."""

    def test_sets_the_active_cancel_event(self):
        import threading as _t
        from notion_to_anki import ui
        ev = _t.Event()
        ui._active_cancel_event = ev
        try:
            ui.cancel_active_sync()
            assert ev.is_set()
        finally:
            ui._active_cancel_event = None

    def test_no_sync_running_is_a_no_op(self):
        from notion_to_anki import ui
        ui._active_cancel_event = None
        ui.cancel_active_sync()          # must not raise

    def test_accepts_hook_arguments(self):
        """gui_hooks may pass arguments; the callback must tolerate them."""
        import threading as _t
        from notion_to_anki import ui
        ev = _t.Event()
        ui._active_cancel_event = ev
        try:
            ui.cancel_active_sync("something", key="value")
            assert ev.is_set()
        finally:
            ui._active_cancel_event = None


class TestRateLimitHandling:
    """A real eMRCS sync lost 3 requests to Notion's rate limiter: the client
    gave up after ~3s of backoff, silently dropping those pages' content."""

    def _http_error(self, code, retry_after=None):
        import urllib.error, io as _io, email.message
        hdrs = email.message.Message()
        if retry_after is not None:
            hdrs["Retry-After"] = str(retry_after)
        return urllib.error.HTTPError(
            "http://x", code, "err", hdrs, _io.BytesIO(b'{"code":"rate_limited"}'))

    def test_honours_retry_after_header(self):
        from notion_to_anki.notion.client import _retry_after
        assert _retry_after(self._http_error(429, 7), fallback=1.0) == 7.0

    def test_retry_after_is_capped(self):
        from notion_to_anki.notion.client import _retry_after, _MAX_RETRY_DELAY
        assert _retry_after(self._http_error(429, 9999), 1.0) == _MAX_RETRY_DELAY

    def test_falls_back_when_header_missing_or_junk(self):
        from notion_to_anki.notion.client import _retry_after
        assert _retry_after(self._http_error(429), 2.5) == 2.5
        assert _retry_after(self._http_error(429, "soon"), 2.5) == 2.5

    def test_waits_out_rate_limits_then_succeeds(self, monkeypatch):
        """Six 429s in a row must still end in a successful request."""
        from notion_to_anki.notion import client as c
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] <= 4:
                raise self._http_error(429, 0)
            class R:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def read(s): return b'{"ok": true}'
            return R()

        monkeypatch.setattr(c.urllib.request, "urlopen", fake_urlopen)
        cl = c.NotionClient("tok")
        assert cl._send(object()) == {"ok": True}
        assert calls["n"] == 5

    def test_gives_up_after_the_budget_with_a_clear_message(self, monkeypatch):
        from notion_to_anki.notion import client as c

        def always_429(req, timeout=None):
            raise self._http_error(429, 0)

        monkeypatch.setattr(c.urllib.request, "urlopen", always_429)
        with pytest.raises(c.NotionError) as ei:
            c.NotionClient("tok")._send(object())
        assert ei.value.status == 429
        assert "rate limit" in str(ei.value).lower()

    def test_non_429_errors_are_not_retried(self, monkeypatch):
        from notion_to_anki.notion import client as c
        calls = {"n": 0}

        def unauthorized(req, timeout=None):
            calls["n"] += 1
            raise self._http_error(401)

        monkeypatch.setattr(c.urllib.request, "urlopen", unauthorized)
        with pytest.raises(c.NotionError):
            c.NotionClient("tok")._send(object())
        assert calls["n"] == 1, "a bad token must fail immediately, not retry"


class TestAnswerlessCards:
    """Real complaint: cards showing a question with nothing on the back.
    'Caval opening at T8' is an empty toggle in Notion, so the card was useless."""

    def _toggle(self, front="Q", children=None):
        t = {"id": "t1", "type": "toggle", "has_children": bool(children),
             "toggle": {"rich_text": [{"plain_text": front, "annotations": {},
                                       "type": "text", "text": {"content": front}}]}}
        if children:
            t["children"] = children
        return t

    def _run(self, monkeypatch, blocks):
        page = "a" * 32
        monkeypatch.setattr("notion_to_anki.notion.client.NotionClient",
                            make_client(page, blocks))
        monkeypatch.setattr(sync_mod, "_process_media", lambda c, *a, **k: c)
        col = FakeCol()
        return sync_mod.run_sync(page_ids=[page], col=col,
                                 config={"notion_token": "t", "page_ids": [page]}), col

    def test_empty_toggle_makes_no_card(self, map_file, monkeypatch):
        r, col = self._run(monkeypatch, [self._toggle("Caval opening at T8")])
        assert r.added == 0 and col.notes == []
        assert r.skipped == 1
        assert any("Caval opening at T8" in w and "no answer" in w for w in r.warnings)

    def test_toggle_with_only_empty_tags_makes_no_card(self, map_file, monkeypatch):
        empty_para = {"id": "p", "type": "paragraph", "has_children": False,
                      "paragraph": {"rich_text": []}}
        r, col = self._run(monkeypatch, [self._toggle("Q", [empty_para])])
        assert r.added == 0 and r.skipped == 1

    def test_image_only_answer_is_kept(self, map_file, monkeypatch):
        """An answer that is just a diagram is perfectly valid."""
        img = {"id": "i", "type": "image", "has_children": False,
               "image": {"file": {"url": "https://x/a.png"}}}
        r, col = self._run(monkeypatch, [self._toggle("What is this?", [img])])
        assert r.added == 1, "a picture answer must not be treated as empty"

    def test_normal_card_unaffected(self, map_file, monkeypatch):
        r, col = self._run(monkeypatch, [self._toggle("Q", [_answer("real answer")])])
        assert r.added == 1 and r.skipped == 0 and r.warnings == []


class TestHasContent:
    def test_recognises_emptiness(self):
        for html in ["", "<p></p>", "<p>  </p>", "<ul></ul>", "&nbsp;", "<div><p></p></div>"]:
            assert not sync_mod._has_content(html), html

    def test_recognises_content(self):
        for html in ["<p>hi</p>", '<img src="a.png">', "[sound:a.mp3]",
                     "<p></p><img src=\"x.png\">", "text"]:
            assert sync_mod._has_content(html), html


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
