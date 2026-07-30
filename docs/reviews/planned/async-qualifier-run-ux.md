# Brief — Async qualifier run UX

Scope, method and leads for an audit nobody has run yet. Leads below are
unverified suspicions from reading the code; the audit confirms or refutes each
one against the running app.

## Scope

The competitor's run, end to end: [`pages/qualifiers.py`](../../../pages/qualifiers.py)
(list → detail → pick a pool → run → submit or forfeit → leaderboard), the
services behind it
([`application/services/async_qualifier/`](../../../application/services/async_qualifier/) —
`service`, `draw`, `scoring`, `rules`, `access`, `live_race`), and the admin
surface that sets it up
([`admin_qualifiers.py`](../../../pages/admin_tabs/admin_qualifiers.py), 496
lines). Feature-gated behind `FeatureFlag.ASYNC_QUALIFIERS`.

## Why this one

This is the **only irreversible participant action in the product**. Picking a
pool draws a permalink and reveals it, starts an elapsed clock, and leaves exactly
two exits: Submit or Forfeit. Everything else a user does in Wizzrobe can be
undone by an admin; a burned qualifier attempt cannot be un-burned. It is also the
surface where the app's one documented unknown bites hardest —
[current-state.md](../../current-state.md) records that the NiceGUI WebSocket
lifecycle across screen lock, backgrounding and resume has never been verified on
real hardware, and this page keeps a live `ui.timer` running for the length of a
speedrun.

## What to measure

1. **Landing to running.** Interactions from `/qualifiers` to a started run.
   Capture the pool-picking copy verbatim
   ([`qualifiers.py:132-152`](../../../pages/qualifiers.py#L132)) and judge
   whether the one-shot nature of the draw is stated *before* the click, not
   after.
2. **Survivability.** With a run in progress: reload the page; navigate away and
   back; background the tab for several minutes; kill and restore the network.
   After each, does the elapsed clock still read correctly, is the permalink still
   retrievable, and is the run still submittable? The clock is a client-side
   `ui.timer` tick ([`:161-176`](../../../pages/qualifiers.py#L161)) — establish
   what it is derived from and whether the server time is authoritative.
3. **The Forfeit button.** Measured at scoping time: `Forfeit` is a flat negative
   button immediately left of `Submit`, with **no confirmation**
   ([`:202-203`](../../../pages/qualifiers.py#L202)). Verify, then measure the blast
   radius — what a forfeit does to the run, the score, the leaderboard, and whether
   any path restores it.
4. **Time entry.** `_parse_hms` ([`:36`](../../../pages/qualifiers.py#L36)) parses
   what the runner types. Drive sloppy input: `1:23:45`, `1:23`, `83:45`, `1h23m`,
   empty, `abc`, negative, a time longer than the window. Record what each does and
   whether the error arrives before or after submission.
5. **Double actions.** Submit twice quickly; forfeit after submitting; start a
   second run while one is active; submit after the window closes. The service has
   rules (`async_qualifier_rules.py`); the question is which refusals reach the
   runner in language they can act on.
6. **The states nobody is in.** `"This qualifier is not open for runs."`,
   `"No pools available to run right now."`,
   `"The leaderboard is hidden until this qualifier closes."`,
   `"You have no runs yet."` — each is one line; check whether it says what to do
   or only what is absent.
7. **Mobile, 390×844.** This is run from a second device while a game is on the
   first. Measure the clock's legibility and the Submit/Forfeit spacing at thumb
   size.
8. **Admin side, briefly.** How a qualifier, its pools and its permalinks get set
   up, and whether a mis-set window or an empty pool is discoverable before a
   runner hits it (lead: F4 of
   [match-operations-ux.md](../match-operations-ux.md) is the same shape — an
   option offered that cannot work).

## Leads to verify

- **Permalink recoverability.** The draw reveals the permalink once on start; check
  whether re-rendering the page (`_render_active_run`) re-shows it, and what a
  runner does if they closed the tab before copying it.
- **Live races** (`async_qualifier_live_race_service`) are a second, racetime-driven
  path into the same qualifier. Check whether a runner can tell which mode they are
  in, and whether the two ever offer both at once.
- **Scoring transparency.** `recompute_par_and_scores` recomputes par when new
  results land — so a runner's score can change after they finish. Verify whether
  anything on the page explains that.
- **QUALIFIER_ADMIN vs staff.** The role gates a management surface; check that the
  admin surface and the worker agree on who may act (same class of bug as
  match-operations F1/F2).

## Fixtures and roles

`seed_dev.py` seeds qualifiers on the `default` tenant (flag on). Drive as a plain
player (`player_two`), and as `staff_user` for the admin half. The feature is
flag-gated, so also run `scripts/ui_flag_sweep.sh` if any shared surface is
touched.

## Deliverable

`docs/reviews/async-qualifier-run-ux.md`, in the shape of the two completed
audits. If the audit turns up something that loses a competitor's run, say so at
the top and flag it for a fix ahead of the rest.
