# Notion → Anki — Configuration

These settings are also editable from **Tools → Notion → Anki** (recommended).

- **notion_token** — your Notion *internal integration* token. Create one at
  <https://www.notion.so/my-integrations>, then **share each target page** with the
  integration (otherwise the API can't see it). Stored locally; never uploaded.
- **page_ids** — list of Notion page IDs (or URLs) to sync. Each becomes a top-level deck
  named after the page; subpages become subdecks.
- **auto_sync_enabled** — turn the background auto-sync timer on/off.
- **auto_sync_interval_minutes** — how often to auto-sync (no lower bound enforced).
- **deck_root** — optional parent deck to nest everything under (blank = top level).
- **on_source_deleted** — what to do when a toggle is removed in Notion:
  `ignore` (default), `suspend`, or `tag`. Cards are never auto-deleted.
