# Devlog

### 2026-09-06 17:04 — Repairing the expiring-image cards in the live collection
**Goal:** repair the existing broken images, and explain the cause.
**Changed:** No source files. This entry records an operation on the user's own
collection, not a code change.
**Worked:** Took two backups first - `med_testing_backup_before_image_repair.apkg`
(196 KB, with scheduling) and a raw copy of `collection.anki2` (6.2 MB), both in
Documents. Recorded the pre-repair state: 208 synced notes, 11 local images,
118 image references still pointing at expiring links. Closed Anki and started a
re-sync of the eMRCS page against the real collection, deck_root "med testing" so
new cards land beside the existing ones. Notes match on their stored
NotionBlockId, so existing cards update in place - no duplicates, no decks moved,
review history untouched. Running under **Anki's own bundled Python (25.09.5)**
rather than the repo venv (26.08.1): a newer anki library can upgrade the
collection schema and lock the user out of their own Anki.
Also confirmed the root cause concretely rather than from memory: Notion signs
image URLs with `X-Amz-Expires=3600`, and `_escape_attr` rewrites the `&`
separators to `&amp;` when the URL goes into the `src` attribute, so the old
substitution - which searched for the raw URL - never matched. The image was
downloaded and then orphaned while the card kept the link that died an hour later.
**Dead ends:** Redirected stdout through a `TextIOWrapper` without line
buffering, so the log stayed empty and the run looked dead; confirmed it was
alive via process CPU/memory and the growing media folder instead.
**Open:** Repair still in progress. Verify afterwards that remote image
references reach 0, no media is missing, and the note count has not jumped.
The 16 broken images under `Testing::*` come from a different Notion page whose
id we do not have, so they are out of scope for this repair.

### 2026-09-06 16:52 — 1.3.0: answer-less cards, and diagnosing the reported blanks
**Goal:** user reviewed real cards and reported broken photos, cards blank on
both sides, and cards with a question but no answer.
**Changed:**
- `notion_to_anki/sync.py` — added `_has_content()` (media counts as content,
  empty tags do not). A toggle whose answer is empty is now skipped with a
  warning naming the question, instead of producing an unstudiable card. The
  blank-question guard, previously silent, now warns too.
- `tests/test_sync_robustness.py` — shared `make_client()` stub serving children
  per block id; +6 tests (99 total).
- `manifest.json` — 1.3.0.
**Worked:** Diagnosed each symptom against the live collection and Notion rather
than guessing. Broken photos: 91 notes under `med testing::*` still hold expiring
S3 URLs because that page is not in `page_ids` and was never re-synced with the
escaping fix — re-running the exact toggles through the current code produces
local files (`notion_52b87cc8….png`, 44 KB; `notion_3308f80f….png`, 34 KB).
"Front but no back": either the answer is only an image (so it looks blank when
the URL has expired) or, for "Caval opening at T8", the toggle has **zero
children in Notion** - genuinely empty at source. Blank-on-both-sides: 4 notes
whose Front and Back are both empty; current code already refuses to create
these, so they are stale rows from an older build.
**Dead ends:** Setting `has_children: True` in the fixtures made
`fetch_block_tree` recurse forever, because the stubs returned the same block
list for every id — the resulting RecursionError was swallowed by a broad
`except` and surfaced as "id map must be written on cancellation". Fixed by the
shared per-id stub.
**Open:** The 91 broken images and 4 stale blank notes are existing rows; they
need a re-sync of the eMRCS page (not currently in `page_ids`) to repair.
AnkiWeb upload remains manual.

### 2026-09-06 15:54 — Release 1.2.0: commit, package, deploy
**Goal:** "update the package so that other people using this add-on will be updated too".
**Changed:**
- `notion_to_anki/manifest.json` — 1.1.0 -> 1.2.0 (1.1.0 was never published).
- `NotionSync_for_Anki.ankiaddon` rebuilt, 21 entries, no state, no token.
**Worked:** Committed the cross-machine batch as c4d944b and pushed; remote hash
verified against local. Fresh-install simulation still passes on the 1.2.0
package. Deployed and confirmed all 21 installed files are byte-identical to the
repo, Anki restarts clean, and the real collection is untouched by the test runs
(208 synced notes, zero eMRCS decks - every run used a temp collection).
**Dead ends:** Told the user my add-on was breaking AnkiConnect, based on one
startup where the API did not answer within 80s while a disabled-add-on restart
answered in 2s. That was a bad inference from a single slow start: with the
add-on enabled a clean restart answers in **3s**, and the add-on imports and
registers all three hooks fine. The slow start was almost certainly recovery
work after I had killed Anki mid-operation several times. Separately, a
`sha256sum` comparison reported every deployed file as different - it was
failing on the Windows path and comparing against an empty string; the Python
comparison is the trustworthy one.
**Open:** AnkiWeb upload is manual - no API, needs a browser login.

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
