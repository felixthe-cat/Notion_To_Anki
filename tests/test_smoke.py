"""Smoke tests — verify the pure (non-Anki) modules import without a running Anki."""


def test_convert_modules_import():
    from notion_to_anki.convert import richtext, toggles, media  # noqa: F401
    from notion_to_anki.notion import client, blocks  # noqa: F401
