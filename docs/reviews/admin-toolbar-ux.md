# The unaudited admin tabs

**Surface:** everything no earlier audit covered — the Online-play trio
(`admin_presets.py`, `admin_racetime.py`, `admin_speedgaming.py`), `admin_webhooks.py`,
`admin_discord_events.py`, `admin_discord_roles.py`, `admin_feedback.py`,
`admin_service_health.py`, `admin_system_config.py`, `admin_randomizer_keys.py`,
the home tabs (`on-air`, `player`, `my-crew`), and the signed-out spectator
bracket views.

**Method:** the loop in [README.md](README.md#method) — services and auth gates
first, then the running app (`./start.sh dev` + `seed_dev.py`) driven with one-off
Playwright scripts as `staff_user`, `proctor_user`, `player_one` and
`super_admin`, on the seeded `default` tenant. Desktop 1500 px and phone
390/470 px. Every finding below was reproduced in the browser; nothing here is
`code-read` only.

The decisive technique was **reading the server log, not the screen.** Two of the
three headline findings produce *no* visible symptom at all: the control renders,
the click does nothing, and the traceback goes to the log. A screenshot sweep —
which is what the previous audits' harness does — passes them all.

---

## Summary

The tabs are, as *surfaces*, in good shape: every dialog's error paths are
handled precisely (probing six of them produced "Preset name is required",
"Settings must be valid JSON: …", "Webhook URL must use https://", "A profile
name is required" — each with the dialog left open), every table has a mobile
card, and no page overflows its viewport at either width.

What was broken was the wiring behind them.

1. **Eleven of the fifteen admin Refresh buttons did nothing**, silently — and
   the errors they logged were actively misleading.
2. **SpeedGaming's Add and Edit buttons were dead**, by the same cause. Creating
   an event link — the only way to configure the sync — was impossible from the UI.
3. **`{'hidden': True}` hid nothing on desktop**, so seven tables led with a raw
   primary key while correctly hiding it on a phone.
4. Four surfaces still printed a match's primary key at a user, including one
   seen by every viewer and one a proctor has to act on.
5. A **cancelled bracket stage kept handing out games**.
6. The match dialog's **Racetime Room section was a dead end**.
7. **Service Health named a problem with no route to it**, and a webhook's
   delivery health was invisible from its row.

All seven are fixed on this branch. What follows is what each one was.

---

## Confirmed defects

### 1. A refresh button spawned from a click loses its tenant (11 of 15 tabs)

`ui.button(icon='refresh', on_click=lambda: background_tasks.create(reload()))`
is the shape, repeated across the admin tabs. A task created in a *client event
handler* has neither the tenant contextvar nor the client stash
`get_current_tenant_id` falls back to — NiceGUI clears the slot stack for
background tasks, and `app.storage.client` raises inside one. So the first
scoped query in the reload raises, NiceGUI logs it, and the button does nothing.

Measured by clicking the refresh control on all fifteen tabs and attributing each
new server-log line to its click:

| Tab | What the server logged |
|---|---|
| Presets, Discord Roles, Stream Rooms, Users | `No tenant in context.` |
| Webhooks | **`Only Staff can view webhooks`** |
| Racetime, Discord Events | **`You do not have permission to manage sync configuration`** |
| SpeedGaming | **`The SpeedGaming Schedule Sync feature is not enabled for this community.`** |
| Equipment, Feedback | `AwaitableResponse must be awaited immediately after creation or not at all` |
| Tournaments, Brackets, Qualifiers, Vol. Roster, Triforce Texts | *(nothing — these already rebind)* |

The four bolded rows are the worrying ones. The click was a **staff user**, on a
community with **SpeedGaming enabled**. Both refusals are correct given what the
code could see: with no tenant, `get_user_from_discord_id` resolves no actor and
`FeatureFlagService` resolves no flags, so the gates refuse honestly. A log
reader chasing this would have gone looking for a permissions bug that does not
exist.

Equipment and Feedback fail differently and for a second reason:
`background_tasks.create(_render_table.refresh())` *calls* `.refresh()` when the
lambda runs, producing an `AwaitableResponse` that is then awaited too late.

**Fixed** by `theme.tables.admin_crud.refresh_button`, which captures the render
context during the page build — where it is still live — and rebinds it around
the call, invoking `refresh` *inside* the task so both shapes work. The one
legitimate exception is `/platform`'s Service Health board, whose loader probes
the whole install and takes no tenant; it opts out with a
`# refresh-context: exempt` comment, the same idiom as `# mobile-grid: exempt`.

#### 1b. The same cause, one layer over: My Crew's two buttons

Having found the shape, the audit clicked every *other* `background_tasks.create`
handler in `pages/` and watched the log. One more was dead, and it is the worse
one because it is a volunteer's, not an admin's.

`my_crew.py`'s `acknowledge` and `withdraw` both opened with
`client = context.client` — *inside* the coroutine. In a detached task the slot
stack is empty and that line **raises** rather than returning `None`, so both
handlers died on their first statement. **Confirm I can cover this** and
**Withdraw** did nothing: no notification, no 500, nothing on screen. My Crew
exists because [the crew audit](README.md) found the volunteer had no surface of
their own; its two actions had never worked from it.

The client now arrives from the call site, and `acknowledge` does its scoped
service call and refresh *inside* the block rather than only the `ui.notify` —
the tenant fallback reads the client stash, which only exists in there.

`check_slot_context.py` caught the related shape (a `ui.*` call in a background
task with no slot) but not this one, because the offending line looks like an
ordinary capture — and in this case was followed by a correct `with client:`
that satisfied the existing check completely. The hook now carries a second
check for it: any coroutine handed to `background_tasks.create` that reads
`context.client` from inside is a hit, with no guarded position available,
because the value is not in the task at all. Tests in
`tests/test_hook_background_client.py`.

The other handlers clicked and found sound: the randomizer-key Save and Clear,
the profile timezone select, SpeedGaming's delete and sync-now, and the preset
import — all of which already take `context.client` as a parameter.

### 2. SpeedGaming could not be configured at all

`open_link_dialog` is `async` (it loads the tournament options), so both entry
points route it through `background_tasks.create` — with the same missing
rebind. `_tournament_options()` raised `No tenant in context`, the exception was
swallowed, and **Add Event Link** and the row's **Edit** pencil did nothing on
screen. The row's *delete* and *sync now* handlers in the same file were fine,
because they take `context.client` and enter it. The dialog openers now do too.

This was the costliest finding in the set: an event link is the only thing that
makes the SpeedGaming sync do anything, and there was no way to create one.

### 3. `hidden` was a convention only half the app honoured

`{'name': 'id', 'label': 'ID', 'field': 'id', 'hidden': True}` appears in seven
column lists. The intent is plain — keep the primary key in the row dict for the
row-action handlers, don't show it. `theme/tables/mobile_grid.py` honours it when
building the phone card. **Quasar's `QTable` has no such column property**, so
the desktop table painted it regardless.

The result is a divergence that a mobile-first check would never surface and a
desktop check would read as intentional: on a phone the Presets card shows
Randomizer / Name / Description; on a desktop the same table leads with `1 2 3 4
5 6`. Discord Events was the worst, its rows sorted by tournament name under a
leading column reading `7 8 6 11 10 5 9 3 4 1 2` — which reads as a broken sort.

**Fixed** by `apply_column_visibility`, which translates the convention into
Quasar's `visible-columns` prop. The row dicts are untouched, which is the point:
`props.row.id` and `row_key='id'` keep working, verified by opening the edit
dialog on every affected table and confirming it still pre-fills from the clicked
row.

**Stream Rooms** was the one table whose id column was deliberate, and it was
worse than the rest: the primary key was the table's *only* edit affordance —
"click the **1** to rename Stage 1" — while the sibling Tournaments tab already
told users to click a *name*. The name carries the link now.

### 4. Four surfaces still quoted a match id

`application/utils/match_labels.py` exists for this and its docstring states the
rule. These had not been through it:

- **On Air** (`stage_timeline.py`) printed `Match #27` on every card, to every
  viewer including signed-out spectators. The card already gives the time, the
  stage, the tournament and the players, so for anyone but an admin the id was
  the only thing on it they could not use. An admin now gets `Open in Schedule`,
  deep-linked with `?match_id=` — the previous link went to the unfiltered board.
- **The result dialog**: `Enter Match Results - Match #17`.
- **The station dialog**: `Check in — Match #17`.
- **The station picker**, which is the one that cost time: an occupied station
  read `Station 4 — in use (match #23)`, and `assign_stations` refused with the
  same string. A proctor who finds a station taken has to go and find the people
  sitting there; the primary key is the one identifier that cannot help them.

Both station strings now name the matchup, resolved in
`application/services/match/_station_copy.py` — one query for the whole picker,
or one only on the refusal path.

### 5. A cancelled bracket stage kept handing out games

`cancel_stage` flips the *bracket's* state and leaves its matchups `OPEN`, by
design — the played results stay as history. But `open_matches_for_user` filters
only on the matchup's state, so the seeded **Bracket Demo — Cancelled** stage was
still listed under "Upcoming matches to schedule" on the player dashboard, with a
live **Schedule game 1** button. `schedule_bracket_match` checked only the
matchup too, so the click would have created a real `Match` in an abandoned
stage.

Worth noting what made this findable: the seed's own docstring claims the
cancelled stage is "visible without anyone having to abandon a demo bracket by
hand… and its absence from every public view". The public *bracket* view does
hide it (`/brackets/3` signed out returns "Bracket not found"). The player
dashboard did not.

Both listings now exclude a cancelled stage, and the service refuses one
outright — a stale dialog, the REST route and the admin's link picker all arrive
there too.

### 6. The Racetime Room section was a dead end

With a room attached, the match dialog rendered
`f'{room.slug} — {room.status.value}'` and returned. Three things wrong with one
line: the slug was not a link (racetime rooms live at `racetime.gg/<slug>`, and
the bracket watch-link code a few modules away already built that URL), the
status was the raw enum the bot writes (`in_progress`), and
`RaceRoomService.cancel_room` — reachable over REST, gated there on
`can_manage_sync`, and covered by tests — had **no web surface at all**. Calling
off a room opened by mistake meant the API or racetime.gg itself.

The section now links the slug (via a `RacetimeRoom.url` property both callers
share), labels the status, and offers **Cancel race room** to `can_manage_sync`
when there is still something to stop. The confirmation says what it does and
does not do: Wizzrobe stops treating the room as live, and the room itself stays
open on racetime.gg.

---

### 7. Two boards that reported a problem and offered nothing to do about it

**Service Health** reported Challonge · *Credential warning* · "Token expiring
soon", under a blurb telling the reader to "reconnect before it becomes an
outage" — with no link to the tab where reconnecting happens. This is the
per-row-route-out finding the admin-reports audit shipped a fix for, in a place
that audit did not reach. The row now offers **Reconnect on the Challonge tab**.
The rule is deliberately narrow: a racetime bot is platform-managed and granted
by a super-admin, so a community's staff can do nothing about an unhealthy one
and get no link — a link that lands somewhere unable to help costs the reader
the trip before they learn that. (The `Category` column also stopped printing
the probe's machine slug: `racetime` → `Racetime`.)

**Webhooks** carried an Active toggle and nothing else, so a webhook whose last
twenty deliveries all 5xx'd looked exactly like a healthy one — the failures
recorded, and two clicks away behind the per-row history dialog. The list now
carries a **Last 24h** column: blank when nothing was sent (a quiet community is
not a problem), `N delivered` when everything landed, and `2 of 3 failed`
leading with the number the operator is looking for. One aggregate query for the
whole list, not one per row. `seed_dev.py` now creates the failing state so it
is visible in a dev environment.

## What the audit checked and found sound

Recorded so a later pass does not re-derive it:

- **Error paths.** Six dialogs probed with empty and junk input (preset with no
  name, preset with malformed JSON, webhook with no name, webhook with a
  non-`https` URL, race-room profile with nothing filled in, SG link with no
  tournament). Every one produced a specific message and left the dialog open.
- **Horizontal overflow.** Measured at 1500 px and 390 px across the schedule
  board, presets, webhooks, discord events, on-air and feedback: the page body
  never exceeds the viewport, and the one table that is wider than its container
  (the schedule board, 1682 px in a 1136 px container) scrolls inside it, which
  is the documented rule.
- **The Randomizer Keys tab** is the model the other integration tabs should
  copy: per-key description, issuing authority named, a `Configured` state, and
  an explicit note that stored values are never shown again.
- **My Crew** is the reference for match copy — *"Player Four vs Player Two
  (Wizzrobe Dev Tournament, 2026-08-01 18:08 EDT)"* — and is what the four
  surfaces in finding 4 now match.

## Deliberately not changed

- **`/platform`'s tenant and bot id columns.** A super-admin genuinely refers to
  tenants by id in support and logs; this is an operator surface, not a community
  one, and the rule in finding 3 is about community-facing copy.
- **The proctor board's `#` column.** The one place a match id is doing a job
  for a human: a proctor calls a match out by number across a room. It stays,
  read-only, and the board keeps no edit link.

  Its neighbour did *not* stay. The admin Schedule board's ID column was the
  same shape as Stream Rooms' — the primary key as the only edit affordance —
  and after review it got the same treatment: the column is now a labelled
  pencil in the same first-column slot, on the desktop table and the mobile
  card alike. The id remains what `?match_id=`, the reports and the audit log
  key on; it is just no longer a control nobody can guess is a control.
- **`Showing match #17 only`**, the board's deep-link filter chip. Naming the
  match would need the (currently sync) page builder to load it, and the row it
  is explaining is directly below.

## Still open

*(Nothing. The one item left open at first write — feedback's one-directional
loop — was scoped and shipped; see below.)*

## Shipped after review

**Feedback was one-directional.** A user asks *"Who do I ask about getting my
racetime name fixed?"* through the in-app form; staff could only **Mark
reviewed**, which was one-way, and the submitter had no way to learn anything
had happened. The [notification-is-one-directional](README.md#cross-cutting-themes)
theme in its purest form, and the one finding this audit recorded rather than
fixed, because closing it is a feature and the scope was the owner's call.

The scope chosen: **no DM**, in-app status only. **Review is reversible** (a
mis-click used to drop a submission out of the only queue anyone looks at, with
no way back), and a person's own submissions carry their status on their
profile — *Read by staff* / *Not read yet*. The staff queue's badges stopped
printing the raw enum too.

The subsystem is now gated behind `FeatureFlag.FEEDBACK`, `established=True`
with a backfill migration so gating it does not make it vanish for communities
already collecting feedback. Both halves of the gate are real: the drawer item,
the admin tab and the profile card all hide, *and* every public method on
`FeedbackService` carries `@requires_feature`.
