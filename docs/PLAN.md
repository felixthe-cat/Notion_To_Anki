# Implementation Plan — Notion_To_Anki

## 1. Goal

A self-contained Anki add-on that pulls a Notion page (and its subpages) directly via the
**official Notion API** and writes flashcards straight into the user's Anki collection.
No AI, no hosted server, no paywall. We replicate notion2anki's *paid* tier (unlimited
pages/notes, fast sync) for free by simply not imposing artificial limits.

## 2. How notion2anki works (what we're matching)

| Feature | Free tier (theirs) | Pro tier (theirs, ~$1.40/wk) | Us |
| --- | --- | --- | --- |
| Notion pages | 3 | Unlimited | **Unlimited** |
| Notes per page | 50 | Unlimited | **Unlimited** |
| Auto-sync interval | 30 min | 5 min | **User-configurable** |
| Toggle → card | ✅ | ✅ | ✅ |
| Subdecks | ✅ | ✅ | ✅ |
| Images / audio | basic | advanced | ✅ |
| LaTeX | basic | advanced | ✅ |
| Cloze | basic | advanced | ✅ (later) |

Their paywall is artificial throttling on a hosted service — the underlying conversion
(open source at [2anki/server](https://github.com/2anki/server), AGPL) has no such limits.
Because an Anki add-on runs *inside* Anki with full collection access, we don't even need
a server: we fetch from Notion and write cards locally.

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Anki (add-on runs inside, has `anki` + `aqt` APIs)      │
│                                                          │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────┐  │
│  │ UI (Qt)    │──▶│ Sync engine  │──▶│ Anki collection│ │
│  │ config +   │   │              │   │ (decks/notes)  │  │
│  │ "Sync now" │   └──────┬───────┘   └───────────────┘  │
│  └────────────┘          │                               │
└──────────────────────────┼───────────────────────────────┘
                           │ HTTPS (Notion REST API)
                           ▼
                  ┌──────────────────┐
                  │  api.notion.com  │
                  └──────────────────┘
```

**Why direct Notion API (not HTML export):** live sync, structured blocks (toggles,
equations, annotations, images come back as typed JSON), and incremental updates by block ID.

## 4. Notion API mapping

User creates a free **internal integration** at notion.so/my-integrations, copies the
token, and shares the target page with it. The add-on then:

- `GET /v1/pages/{id}` → page **title** → deck name.
- `GET /v1/blocks/{id}/children` (paginated) → top-level blocks.
- **`toggle`** block at top level → one card.
  - Toggle's `rich_text` → **Front**.
  - Toggle's children (non-toggle) → **Back**.
  - Toggle's children that are themselves **`toggle`** → **Extra** field, each wrapped:
    `<details><summary>{nested front}</summary>{nested back}</details>`.
- **`child_page`** block → recurse → new **subdeck** `Parent::Child`.
- Rich text `annotations` (bold/italic/underline/strikethrough/code/color) → inline HTML
  + CSS classes.
- **Equations** (inline `equation` rich text + `equation` block) → MathJax delimiters
  `\( … \)` / `\[ … \]` (Anki ≥ 2.1 renders MathJax natively — no LaTeX install needed,
  no rendering issues).
- **Images** (`image` block, external or Notion-hosted file) → download bytes → store via
  `col.media.write_data()` → `<img src="hash.ext">` in the card.

## 5. Note type

Custom model **"Notion Toggle (3-field)"**: `Front`, `Back`, `Extra`.
- Card template shows Front on question; Back + Extra on answer.
- Bundled CSS reproduces Notion text colors/highlights.
- Stable identity: store a `notion_block_id` in a hidden field (or first-field GUID) so
  re-syncs **update** existing cards instead of duplicating.

## 6. Sync semantics

- Map each Notion toggle block ID → Anki note GUID (persisted in `user_files/`).
- On sync: add new, update changed (compare Notion `last_edited_time`), optionally
  flag/suspend cards whose source toggle was deleted (configurable, never auto-delete).
- Manual "Sync now" button + optional background auto-sync timer (user sets the interval —
  this is the "paid" feature we give away).

## 7. Project layout

```
notion_to_anki/           # the add-on package (this is what ships to AnkiWeb)
  __init__.py             # entry: hooks into Anki menu
  config.json             # default config (token, page IDs, interval)
  config.md               # config UI help
  notion/
    client.py             # Notion REST client (urllib, no external deps*)
    blocks.py             # block tree fetch + pagination
  convert/
    richtext.py           # rich_text -> HTML (annotations, colors, equations)
    toggles.py            # toggle tree -> {front, back, extra}
    media.py              # image download -> collection media
  anki_io/
    models.py             # ensure note type exists
    decks.py              # deck/subdeck creation
    writer.py             # add/update notes idempotently
  sync.py                 # orchestrates a full sync
  ui.py                   # Qt dialog + menu actions
tests/                    # pytest, with recorded Notion API fixtures
docs/PLAN.md
```
\* Anki bundles `requests`; we'll prefer the stdlib but may use it if already available.

## 8. Milestones

1. **M1 – Skeleton:** add-on loads in Anki, adds a menu item, config dialog stores token.
2. **M2 – Read Notion:** fetch page title + block tree, print to console.
3. **M3 – Core conversion:** top-level toggles → 3-field cards in a deck named after the page.
4. **M4 – Nested toggles:** `<details>` Extra field.
5. **M5 – Subpages → subdecks** (recursive).
6. **M6 – Rich content:** annotations/colors, LaTeX (MathJax), images.
7. **M7 – Idempotent re-sync** (update, no duplicates).
8. **M8 – Auto-sync timer + polish**, then package `.ankiaddon` and publish to AnkiWeb.

## 9. Testing

- Unit tests on the converters with saved Notion JSON fixtures (no network).
- A sample Notion page covering: nested toggles, colors, inline+block LaTeX, images,
  subpages — used as the end-to-end golden test.

## 10. Resolved decisions

- **Notion source:** Official Notion API only (free internal-integration token). No HTML-export
  path for v1. → drives §4, §3.
- **Sync trigger:** Manual "Sync now" button **plus** an optional background auto-sync timer
  with a user-configurable interval (default e.g. 15 min, no lower bound enforced — this is the
  feature notion2anki paywalls). → §6.
- **Note type:** Single custom 3-field model `Front / Back / Extra` (§5). Cloze support is a
  later enhancement, not in the core milestones.
- **License:** AGPL-3.0 (keeps derivatives open; matches Anki/2anki ethos). Changeable on request.

## 11. Build handoff (read this first if you're building in a fresh session)

This plan is the spec. Build order is the milestones in §8 (M1 → M8). Notes for the builder:

- **Target Anki:** 2.1.x on the modern Qt6 stack. Use the `anki` (collection) and `aqt`
  (GUI) packages that ship inside Anki — do not pip-install Anki. Test by symlinking/copying
  `notion_to_anki/` into Anki's `addons21/` folder.
- **No AI anywhere** in the pipeline — pure deterministic parsing. Hard requirement.
- **Dependencies:** prefer the Python stdlib (`urllib`, `json`). Anki bundles `requests`;
  use it only if convenient. Do **not** require AnkiConnect — write to the collection directly.
- **Notion API specifics to verify against current docs (api.notion.com, version header
  `Notion-Version`):** block pagination via `start_cursor`/`has_more`; toggle children are
  fetched with a separate `GET /blocks/{id}/children`; `image` blocks expose either
  `external.url` or a time-limited `file.url` (download immediately); inline LaTeX arrives as
  `rich_text` items of type `equation`, block LaTeX as an `equation` block.
- **LaTeX:** emit MathJax delimiters (`\( \)`, `\[ \]`); do not invoke the legacy LaTeX/dvipng
  pipeline — MathJax avoids install/rendering issues.
- **Idempotency is critical:** persist the `notion_block_id → note GUID` map in `user_files/`
  (survives add-on updates) so re-syncs update, never duplicate. Never auto-delete cards.
- **Secrets:** the Notion token lives in Anki's add-on config / `user_files/`, never committed.
- Land tests (§9) alongside each converter using saved Notion JSON fixtures (offline).
