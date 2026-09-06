# Decisions

### ADR-1: Keep the Anki 23.10 floor rather than requiring a Qt6-only Anki
**Context**
The UI uses Qt6-style scoped enums (`Qt.WindowModality.ApplicationModal` and
nine others). Anki shipped Qt5 builds up to 24.11; 25.02 onward is Qt6 only.
`min_point_version` is 231000 (Anki 23.10), so a Qt5 user can still install
this add-on, where those enum spellings do not natively exist.

**Options considered**
1. Raise the floor to 250200 so only Qt6 builds can install it.
   Drawback: also locks out everyone on Anki 23.10-24.11 running the *Qt6*
   build, who would work fine today. Turns a hypothetical crash into a
   guaranteed "unsupported" for a real population.
2. Keep 231000 and rely on Anki's PyQt5 compatibility shim, which aliases
   scoped enums for add-ons that import Qt through `aqt.qt`.
   Drawback: depends on Anki's shim, and silently breaks if any future edit
   imports from `PyQt6` directly instead of `aqt.qt`.
3. Write our own enum compatibility helpers.
   Drawback: ten call sites of indirection to serve a shrinking population;
   more code than the problem is worth.

**Chosen + why**
Option 2. Anki's add-on documentation states that Qt6 code works on Qt5 builds
provided Qt classes are imported from `aqt.qt`. Verified this holds: all 17 Qt
imports go through `aqt.qt` and there are zero direct PyQt imports, so the
widest range of Anki versions is supported at no cost.

**Reversible?** Cheap - one number in `manifest.json`.

**Guard:** if a future change imports from `PyQt6` directly, this decision is
void and the floor must move to 250200.

### ADR-2: React to Notion's 429s rather than throttling every request
**Context**
Notion allows roughly 3 requests/second. A large page tree is thousands of
requests, so rate limiting is routine. The old client gave up after ~3s of
backoff, and losing one request drops that page's content from the sync.

**Options considered**
1. Reactive: retry on 429, honouring the `Retry-After` header, with a larger
   attempt budget.
   Drawback: still eats one rejected request before slowing down, so a heavily
   throttled sync does wasted work and is a little slower than a paced one.
2. Proactive: pace every request to stay under ~3/second.
   Drawback: penalises every sync, including small ones that would never have
   been limited, and hard-codes a published limit that Notion can change.
3. Both: pace *and* retry.
   Drawback: two interacting mechanisms to reason about for a problem one of
   them already solves; the pacing constant becomes a second thing to tune.

**Chosen + why**
Option 1. `Retry-After` is the server telling us exactly how long to wait, which
beats any constant we could pick, and it costs nothing on syncs that are never
throttled. Small pages stay fast; only genuinely throttled runs slow down.

**Reversible?** Cheap - pacing could be added in `_send()` later without
touching callers.

**Evidence gap:** the run that motivated this was contaminated (two concurrent
syncs on one integration, see DEVLOG 2026-09-06 15:04), so the true 429 rate for
a single sync of this page is not yet measured. If a clean run still shows
frequent throttling, revisit option 3.

### ADR-2 follow-up (2026-09-06): evidence gap closed
A single clean sync of the eMRCS page (roughly 1,500 requests over 22 minutes)
produced **zero** 429s. The throttling that motivated ADR-2 came from two
concurrent syncs sharing one integration, not from normal use. The reactive
choice stands and option 3 (adding pacing) is not warranted.
