# What changed for users

Entries describe behaviour built for the next release. Nothing below has been
published to AnkiWeb yet.

- 2026-09-06 — Sync errors now say what to do. A wrong token or a page you
  forgot to share explains the fix instead of showing Notion's raw error data.
- 2026-09-06 — A page you have not shared with your integration is now named as
  a page, not reported as a missing database.
- 2026-09-06 — Quitting Anki during an import now stops it cleanly instead of
  leaving it running against a closing collection.
- 2026-09-06 — The token box hints `ntn_...`, matching the tokens Notion issues
  today (it previously showed the retired `secret_...` prefix).
- 2026-09-06 — You can stop an import while it is running, and it stops within
  about a second. Cards already imported are kept, and running the sync again
  carries on from where it stopped.
- 2026-09-06 — Pictures from Notion now stay on your cards. They previously
  went blank about an hour after importing.
- 2026-09-06 — After a sync you are told how many pictures could not be
  imported, and why: only toggles, cloze text and tables become cards, so a
  picture sitting loose on a page has no card to attach to.
- 2026-09-06 — Repeat syncs are much faster: pictures already downloaded are no
  longer fetched again every time.
- 2026-09-06 — Notion pages that contain no cards no longer create empty decks
  in Anki.
- 2026-09-06 — Text inside Notion columns and synced blocks now comes across
  instead of being dropped.
- 2026-09-06 — Toggles with an empty title are reported as skipped rather than
  disappearing silently.
- 2026-09-06 — Losing or damaging the add-on's internal index no longer causes
  every card to be added a second time.
- 2026-09-06 — Large Notion pages no longer lose content when Notion slows the
  sync down. It now waits as long as Notion asks and carries on, instead of
  giving up after a few seconds.
- 2026-09-06 — Items that were skipped rather than broken are now listed
  separately from errors, so a healthy sync no longer reports "8 error(s)".
- 2026-09-06 — A toggle with no answer in Notion no longer becomes a card you
  cannot study; the summary names the question so you can fill it in instead.
  An answer that is only a picture still counts as a real answer.
