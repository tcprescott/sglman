# Async qualifier run UX — evaluation

**Scope:** the competitor's run and the reviewer's judgement of it —
[`pages/qualifiers.py`](../../pages/qualifiers.py) (list → detail → draw → run →
submit/forfeit → leaderboard), the Review Queue on
[`admin_qualifiers.py`](../../pages/admin_tabs/admin_qualifiers.py), and
[`application/services/async_qualifier/`](../../application/services/async_qualifier/).
Behind `FeatureFlag.ASYNC_QUALIFIERS`. Live races and pool authoring appear only
where the run flow depends on them.

**Method:** read the service, then drove the running app against the seeded
`Dev Async Qualifier` on the `default` tenant (2 runs/pool, 1 reattempt, 3 pools)
as `player_two` and `player_three`, with `staff_user` working the review queue in
a parallel session. Started real runs and spent every one of them: submitted junk
times, an impossibly short time, an impossibly long one, an ambiguous one, and
forfeited one. Tested survivability by reloading, navigating away and back, and
going offline mid-run. Discord DMs were read from the `MOCK_DISCORD` log. Every
number below is measured.

**Headline:** the risky part is solid. The draw is atomic and row-locked, the
permalink survives a reload, and the elapsed clock is derived from the
server's `started_at` so it self-heals after an offline gap — the three things
that could lose a run don't. What is missing sits on either side of the run: the
server times every run and then **ignores its own measurement** when accepting the
runner's claim, and the one destructive control on the page (**Forfeit**) has no
confirmation while its documented remedy (`reattempt_run`) exists in the service
and is wired to nothing.

---

## The measured shape

| Step | Interactions | Copy |
|---|---:|---|
| `/qualifiers` → Open → Start: *pool* | **3** | *"Pick a pool. A permalink is drawn and revealed only when your run starts — and your timer begins immediately."* |
| Start | — | *"Run started — good luck!"* |
| Submit | 2 (time + Submit) | *"Submitted for review!"* |
| Forfeit | **1** | *"Run forfeited."* — no confirmation |

Survivability of an in-progress run (all measured against one live run):

| Event | Elapsed clock | Permalink |
|---|---|---|
| Steady state | ticks each second | shown as a link |
| Full page reload | `0:00:09` → `0:00:12` — correct | **still present** (`https://alttpr.com/en/h/dev-default-bonus-1`) |
| Navigate to `/qualifiers` and back | `0:00:17` — correct | present |
| 8 s offline | frozen at `0:00:17` | present |
| Reconnect | jumps to `0:00:31` — **correct**, recomputed from `started_at` | present |

Time entry (`_parse_hms`, [`qualifiers.py:36-53`](../../pages/qualifiers.py#L36)):

| Typed | Result |
|---|---|
| `abc` | *"Finish time must be numbers separated by ':'"* |
| `-5` | *"Enter a finish time as H:MM:SS"* |
| `0` | *"Finish time must be greater than zero"* |
| `1:2:3:4` | *"Enter a finish time as H:MM:SS"* |
| `1:23` | **accepted → stored as `0:01:23`** |
| `99:99:99` | **accepted → stored as `100:40:39`** |
| `0:00:02` on a run the server timed at `0:00:14` | **accepted, no objection** |

What the reviewer then sees, verbatim, in the Review Queue:

```
Player Four   6000s     Standard Pool   [Approve] [Reject]  VoD
Player Two    362439s   Bonus Pool      [Approve] [Reject]
Player Two    2s        Bonus Pool      [Approve] [Reject]
Player Two    83s       Standard Pool   [Approve] [Reject]
```

Rejecting the 362,439-second run: one click, **no reason prompt anywhere on the
page** (measured), and the runner's DM reads in full: *"Your qualifier run was
rejected."* Their own runs table then shows `rejected` with no explanation.

---

## Root causes

### RC1 — The server measures the run and never uses the measurement

`start_run` stamps `started_at` server-side inside the transaction
([`async_qualifier_service.py:497-503`](../../application/services/async_qualifier/async_qualifier_service.py#L497)),
and the page's ticker derives the clock from it — that is exactly why the clock
survives a reload. But `submit_run` validates the claimed `elapsed_seconds` only
against `0 < x ≤ MAX_RUN_SECONDS` (a week)
([`:512-527`](../../application/services/async_qualifier/async_qualifier_service.py#L512)).
It never compares the claim to `now - started_at`, never stores the measured
duration alongside the claimed one, and the reviewer's card never shows it. The
authoritative number is computed, displayed to the runner for the whole run, and
then dropped.

### RC2 — The page is a two-button terminal for a five-verb service

`AsyncQualifierService` exposes `start_run`, `submit_run`, `forfeit_run`,
`reattempt_run` and `review_run(note=…)`. The player page wires two of them;
the admin page wires `review_run` **without** its `note` argument.

| Service capability | Reachable from a page? |
|---|---|
| `start_run` / `submit_run` / `forfeit_run` | yes |
| `reattempt_run` ([`:556-578`](../../application/services/async_qualifier/async_qualifier_service.py#L556)) — voids a terminal run so its pool slot frees up, requires a reason, capped by `allowed_reattempts` | **no callers anywhere** in `pages/`, `api/`, `mcpserver/` or `discordbot/` |
| `review_run`'s `note` (stored as a run note, [`:627-629`](../../application/services/async_qualifier/async_qualifier_service.py#L627)) | **not passed** by the Review Queue |

The admin *does* configure `Allowed reattempts` (measured on the admin card:
`Runs/pool: 2 · Reattempts: 1`), so a community can grant a remedy that nobody
can spend. Same shape as
[bracket-creation-ux RC1](bracket-creation-ux.md): a capability nobody wired is
invisible rather than merely inconvenient.

### RC3 — Confirmation is spent on nothing, and the irreversible action has none

`forfeit_run`'s own docstring says *"Forfeit is irreversible, scores zero, and
blocks replay unless a reattempt is spent."* The button that calls it is a flat
negative button 16 px to the left of Submit, both 44 px tall, and clicking it
applies the forfeit immediately (measured). The codebase has a
`ConfirmationDialog` used for far smaller things — crew signup, a reversible act,
gets a modal ([crew-signup-ux F8](crew-signup-ux.md#f8--minor--the-confirmation-budget-is-spent-on-the-reversible-action)).

---

## Findings, ranked

### F1 — Blocker · A forfeit is one unconfirmed click, and its remedy is unreachable

Measured: click **Forfeit** → no dialog → `Run forfeited.` → status `forfeit`,
review `approved`, score `0`, permanently. After spending the last pool slot the
page reads *"No pools available to run right now."* and the word "reattempt"
appears nowhere on it (measured `false`), even though this qualifier grants one.

The fix path exists and is one method call. Until it is wired, a mis-click ends a
competitor's qualifier attempt with no in-app recovery — and the admin surface has
no way to spend the reattempt on their behalf either.

### F2 — Critical · A claimed time is accepted without ever being compared to the measured one

Measured: a run the server timed at 14 seconds accepted a claim of `0:00:02`; a
run about 30 seconds old accepted `99:99:99`, normalised to `100:40:39`. Both went
to review as ordinary submissions.

This is not primarily an anti-cheat point — it is a **typo detector nobody
built**. `MAX_RUN_SECONDS` shows the intent ("longer than a week — check the value
you entered"), a week is just an absurd ceiling when `now - started_at` is sitting
right there. The natural shape is a soft warning at submit time ("your timer says
1:14:02, you typed 0:14:02 — which is right?") plus the measured duration on the
reviewer's card.

### F3 — Critical · `1:23` means 83 seconds, and nothing says so

`_parse_hms` accepts `SS`, `MM:SS` and `H:MM:SS` by folding parts into base-60,
with no disambiguation. Measured: `1:23` → `0:01:23`. The field is labelled
*Finish time (H:MM:SS)* with placeholder `1:23:45`, so a runner who types the
same shape one segment short — the single most likely typo in this field — silently
submits a time 60× too fast, and F2 means nothing catches it. The runs table then
shows `0:01:23`, which reads as correct at a glance.

### F4 — Major · A rejection carries no reason, to anyone

Measured: Reject is one click, the page never asks for a reason, the DM says only
*"Your qualifier run was rejected."*, and the runner's table shows `rejected` with
nothing else. `review_run` takes a `note`, stores it via `note_repository`, and no
surface passes one — nor does any surface *display* run notes to the runner. With
F1, a rejected runner has no reason, no appeal, and no reattempt affordance.

### F5 — Major · The reviewer decides from four facts, three of which are raw

The queue card shows name, `NNNNNNs`, pool, and an optional VoD link
([`admin_qualifiers.py:429-450`](../../pages/admin_tabs/admin_qualifiers.py#L429)).
`362439s` is 100:40:39; `6000s` is 1:40:00 — the reviewer is converting seconds in
their head while the page has `_fmt_hms` available in the player module. Absent
entirely: when the run started and finished, the server-measured duration (F2),
which permalink was played, the runner's other runs in this pool, and any note
field.

### F6 — Minor · Nothing tells a runner their score can move after they finish

`review_run` calls `recompute_par_and_scores`, which re-pars the permalink from the
approved set and **rescores every approved run on it**
([`async_qualifier_service.py:636-640`](../../application/services/async_qualifier/async_qualifier_service.py#L636)).
So a runner's score legitimately changes when someone else's run is approved. The
runs table has a `Score` column and no explanation, and the leaderboard has an
`Estimate` column that is never defined on the page.

### F7 — Minor · Pool exhaustion and window closure share one message

*"No pools available to run right now."* is shown when the window is open but the
runner has used every slot, and `get_player_pools` returns `[]` for several other
reasons too (no undrawn permalinks left, slots taken). *"This qualifier is not
open for runs."* covers the window case. Neither tells the runner which situation
they are in or what, if anything, changes it.

---

## What works

- **The draw.** `start_run` row-locks the player, re-checks the active-run and
  per-pool caps inside the transaction, and picks by imbalance-forcing fairness —
  concurrent double-clicks serialise instead of burning two permalinks.
- **Reveal == start, stated up front.** The one-shot nature is in the copy
  *before* the click, which is where it belongs.
- **The clock is server-derived.** Reload, navigation and an 8-second network drop
  all recovered to the correct elapsed time; the permalink was still on the page
  every time. This is the single most important thing on the surface and it is
  right.
- **`_parse_hms`'s rejections** are specific and actionable (`abc`, `-5`, `0`,
  `1:2:3:4` all produce the correct sentence).
- **Information lockdown.** The leaderboard's *"hidden until this qualifier
  closes"* is enforced in the service by a `PermissionError` the page catches, not
  by hiding a widget.
- **Runs are auditable end to end** — start, submit, forfeit and review each write
  an audit row and publish an event.

## Not covered

Live races (the racetime-driven path into the same qualifier), pool and permalink
authoring, the scoring maths itself, the feeds/seasons integration, and the
Discord acknowledge-button path.
