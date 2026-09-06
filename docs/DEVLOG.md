# Devlog

### 2026-09-06 15:46 — Clean acceptance run; warnings split from errors
**Goal:** finish verification, then commit and repackage.
**Changed:**
- `notion_to_anki/sync.py` — `SyncResult` gains `warnings`; skipped blank-titled
  toggles moved there from `errors`.
- `notion_to_anki/ui.py` — the summary lists skipped items under their own
  heading, above real errors.
- `tests/test_sync_robustness.py` — blank-toggle test asserts a warning and no
  error (93 tests).
**Worked:** One clean run of the real page. Cold 22.2 min: 311 cards, 290 image
references, 0 still remote, 0 missing on disk, 53.7 MB media, and **zero rate
limit errors** - confirming the earlier 429s were caused by my duplicate run,
not by the add-on. Warm sync 9.3 min (media cache), 0 added / 311 updated.
Third sync with the id-map deleted: still 311, no duplicates. Lazy decks give
192 decks with 19 empty, against 703 / 629 before.
**Dead ends:** The harness printed "CHECK FAILURES" because its pass condition
required zero errors, but the 8 blank-toggle notices land in `errors`. That was
the harness being wrong *and* a real reporting flaw - a clean sync announced
"8 error(s)" - which is what prompted the warnings split. Two heredoc attempts
to insert the UI block mangled backslash escapes into real newlines; fixed by
building the escape from `chr(92)`.
**Open:** AnkiWeb upload still needs a manual browser login.

### 2026-09-06 15:04 — Wait out Notion rate limits; contaminated measurement
**Goal:** finish the eMRCS acceptance run and make the add-on universal.
**Changed:**
- `notion_to_anki/notion/client.py` — `_get`/`_post` retry loops replaced by one
  shared `_send()`. 429s now honour Notion's `Retry-After` header, back off
  exponentially to a 30s cap, and get a budget of 6 attempts instead of 3.
  Non-429 failures still fail immediately rather than burning retries.
- `tests/test_sync_robustness.py` — +6 rate-limit tests (93 total).
**Worked:** A cold run of the real page surfaced three requests lost to HTTP 429;
the old policy gave up after roughly 3s of backoff, which silently drops that
page's content. The shared `_send()` removes the duplicated retry logic rather
than doubling it.
**Dead ends:** The measurement that produced those 429s was my own fault - I
started the acceptance run twice without checking the first had exited, so two
syncs hit one Notion integration concurrently and doubled the request rate. The
log interleaved two different "SYNC 1" results (254 vs 311 cards), which is what
exposed it. Both processes killed; re-running once, cleanly. Treat any figure
from that run as void.
**Open:** Clean acceptance run in progress. Nothing committed or repackaged.
Note the source page has grown since the 11 Aug probe (123 cards -> ~254+), so
older expected-count figures no longer apply.

### 2026-09-06 14:51 — Cross-machine audit: friendly errors, close-safety, Qt5 check
**Goal:** "check whether this add-on works on other people's computers... make it universal".
**Changed:**
- `notion_to_anki/notion/client.py` — `NotionError` now carries `.status`/`.code`;
  Notion's raw JSON error body is translated into an actionable sentence
  (bad token, page not shared, bad ID, rate limited). ASCII-only, since the text
  can reach logs on non-UTF-8 systems.
- `notion_to_anki/sync.py` — when an ID resolves as neither page nor database,
  report the *page* failure; the database attempt told users their page was a
  "missing database".
- `notion_to_anki/ui.py` + `__init__.py` — added `cancel_active_sync()`, wired to
  `profile_will_close`, so quitting Anki stops an in-flight sync instead of
  leaving a background thread calling into a closing collection.
- `notion_to_anki/ui.py` — token placeholder `secret_...` -> `ntn_...` (Notion
  changed the prefix; the old hint made a correct token look wrong).
- `tests/test_sync_robustness.py` — +10 tests (87 total).
**Worked:** Audited for machine-specific assumptions: no absolute paths, no OS
branching, no direct PyQt imports (all via `aqt.qt`, which is what keeps Qt5
builds working), every `open()` sets an encoding, screenshot filenames match
on case-sensitive filesystems, and every Anki API used still exists in 25.09.5.
Deck naming survives emoji, newlines, `::`, slashes and 200-char titles.
Fresh-install simulation (numeric folder, no state) passes 18/18.
**Dead ends:** Chained string replaces on the error-message block produced nested
double quotes inside an f-string — a parse error; rewrote the block wholesale.
The package leak check then matched the new `ntn_...` placeholder, so it now
requires 20+ trailing characters to count as a real token.
**Open:** eMRCS acceptance run still in progress; nothing committed or
repackaged yet. AnkiWeb upload cannot be automated - it needs a browser login.

### 2026-09-06 14:42 — Re-run eMRCS verification; fix stranded-image counter
**Goal:** "re-run the verification then commit and repackage".
**Changed:**
- `notion_to_anki/sync.py` — `SyncResult.pages_without_cards` renamed to
  `pages_with_lost_images`; it now increments only when a page actually strands
  an image, instead of on every card-less page.
- `notion_to_anki/ui.py` — completion dialog reads the renamed field.
- `tests/test_sync_robustness.py` — assertions updated; added a case pinning
  that a card-less page which loses nothing is not counted (77 tests pass).
**Worked:** Rebuilt the eMRCS acceptance harness (the previous one was lost with
the temp folder) and started a cold/warm/id-map-deleted run against the real
page via `NOTION_TOKEN` + `DATABASE_ID`. Credentials re-verified. Offline checks
green: 77 tests, clean compile, no PEP 585/604 syntax outside deferred
annotations (Anki 23.10 floor is Python 3.9).
**Dead ends:** First attempt to patch the harness produced an f-string with
nested double quotes — invalid before Python 3.12, so it failed to parse. Split
the `getattr` out to its own statement. Also note the previous session's run
died (exit 4) and its logs were wiped, so it never yielded a result.
**Open:** Verification still running; nothing committed or repackaged yet. The
in-flight run reports the pre-rename counter, since it loaded the old module.
