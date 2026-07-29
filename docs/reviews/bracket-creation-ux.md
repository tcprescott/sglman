# Bracket creation UX — evaluation

**Scope:** authoring a native bracket, from an empty tournament to a started
stage — the Admin → Brackets tab
([`pages/admin_tabs/admin_brackets.py`](../../pages/admin_tabs/admin_brackets.py)),
its Create dialog and its Manage dialog. Result reporting, the public view and
the scheduling seam appear only where the authoring flow depends on them.

**Method:** read the bracket service, config schema, engines and REST router,
then drove the running app in a headless browser as `staff_user` against a
seeded `default` tenant — created a stage from scratch on an unlinked
tournament, built an 8-entrant field, started it, probed every error path
(duplicate stage, Challonge-linked tournament, complete-with-open-matches,
advance-with-no-next-stage, post-start seed editing) and re-measured the Manage
dialog at 32 entrants. Every number below is measured. Findings were then
cross-checked by independent reviewers reading the same source; where a
reviewer refuted a claim, the corrected version is what appears here and the
correction is noted.

**Headline:** the service layer is good — careful guards, honest docstrings, a
real dry run for advancement, atomic seed validation. The admin page is a thin
RPC console over about two-thirds of it. The flow does not feel clunky because
the domain is modelled badly; it feels clunky because the page exposes the write
methods someone remembered to wire, in the shape the service exposes them, with
no undo and no rehearsal.

---

## The measured shape of the flow

Landing on Admin → Brackets to a **started 8-player single-elimination stage**:

| Step | Interactions | Notes |
|---|---:|---|
| Select tournament | 2 | no default, no memory across reloads |
| Open Create, name it, submit | 3 | Format defaults to Single elimination |
| Open Manage | 1 | |
| Add 8 entrants | **24** | focus + type + click Add, once per entrant, each a server round trip |
| Enroll 8 entrants | **8** | one click per row |
| Start bracket | 1 | |
| **Total** | **≈39** | for 8 players, seeding left to the automatic fallback |

At the sizes this feature is for, a 32-player field is **≈135 interactions**.
The Manage dialog at 32 entrants measures **3,440 px of scroll in a 931 px
viewport — 3.7 screenfuls — containing 34 form fields**, and it prints every
entrant's name **twice**: once under "Roster — enroll into this stage"
(`admin_brackets.py:223-231`), once under "Enrolled entries" (`:253-265`). 64
rows for 32 players; 128 for 64.

This cost is paid **once per tournament**, for stage 0 only — `advance_stage` is
a bulk enroll *and* auto-seed for every later stage
([`_bracket/multistage.py:64-71`](../../application/services/_bracket/multistage.py#L64)).
The machinery for doing this well already exists; stage 0 just never got it.

---

## Root causes

Five structural things produce nearly all the friction. Everything in the
findings list below is a symptom of one of them.

### RC1 — The page is an RPC console over `BracketService`, not a tool for running an event

Every control maps to exactly one service method and the four row actions are
the four lifecycle verbs. Nothing composes calls into a task. Two consequences
follow mechanically:

- **A capability nobody wired is invisible, not merely inconvenient.**
  `update_bracket`, `delete_bracket`, `drop_entrant`, `set_best_of`, the
  `tie_breaks` argument and `standings()` are all reachable from REST or MCP and
  from nowhere on this page.
- **A task needing N calls costs N round trips and N full rebuilds.**

The dev seed script is the proof:
[`scripts/seed_brackets.py`](../../scripts/seed_brackets.py) drives the whole
flow in ~450 lines and passes `config={"rounds": {...}}` at create time because
the dialog has no field for it. The script is doing the composition the UI
refuses to.

### RC2 — The Create dialog is a form over the `BracketConfig` JSON blob, not over the operator's decisions

It renders the union of all format fields because the schema is a union
([`bracket_config.py:106-140`](../../application/services/bracket_config.py#L106));
it omits `grand_final_reset` and `tiebreakers` because nobody wrote widgets; it
does no cross-field validation because pydantic does none and the dialog does
none. `fmt_in` (`admin_brackets.py:593-595`) has **no `on_change`** — nothing in
the dialog reacts to the format you pick.

Notice what the form does *not* ask: "is this a Bo3?", "does the grand final
reset?", "how many rounds?" — the three questions a tournament organizer answers
first. Those are engine inputs rather than top-level `BracketConfig` fields, so
the blob-shaped form never surfaced them.

### RC3 — Authoring and operating share one surface, and only operating got a state machine

The service's lifecycle verbs are meticulously guarded — DRAFT/ACTIVE/COMPLETE
checks on every method, ordering constraints on `start_bracket`, an auto-complete
path for elimination. The authoring verbs — edit, delete, un-enroll, retire,
re-link — were either never wired or never written.

The page is state-blind in the opposite direction: four buttons rendered
unconditionally on every row, dead controls left enabled in the Manage dialog,
no state badge, no counts in the table. The service knows the state machine
perfectly; the presentation layer knows nothing about it, so it can neither hide
what will not work nor offer what would.

### RC4 — There is no rehearsal step, so every commit is a guess — and the commits are one-way

DRAFT exists precisely as a private authoring state
([`theme/brackets/visibility.py`](../../theme/brackets/visibility.py) says so),
the engines are pure and ORM-free, and `get_advancing_preview` proves the team
knows how to build a dry run. Yet nothing renders a DRAFT stage: `engine.generate`
has exactly one call site in the codebase
([`_bracket/generation.py:120`](../../application/services/_bracket/generation.py#L120))
and it is inside the write path. The operator's first sight of the bracket is
after `start_bracket`, which is simultaneously the draw, the publish and the
notification.

The confirmation budget is spent backwards — on Complete (which auto-fires on
elimination anyway) and on Advance (which already has a preview), and not on
Start. The substrate for a preview/publish flow is fully built and entirely
unused.

### RC5 — The knowledge is in docstrings; the UI ships captions

Every rule an operator can break is documented, often beautifully: the two-level
roster, DRAFT = unpublished, best-of semantics, where the advancement rule
lives, what the user link buys, why player match requests get disabled. None of
it reaches the screen. The messages themselves are good English, but they are
written from the service's point of view, arrive at the point of *failure*
rather than the point of *decision*, and land in a 5-second toast that cannot be
re-read.

Where the codebase talks to itself about semantics it even contradicts itself:
`set_round_metadata` says round chrome is "display-only (it never affects the
persisted graph)" (`bracket_service.py:206-208`) while `RoundConfig` says
`best_of` "is **semantic** … the scheduler and clinch logic both read it"
(`bracket_config.py:75-81`). The UI caption inherited the wrong half.

---

## Findings, ranked

### P1 — Blocker · No Edit and no Delete for a stage; `format` is immutable even over REST

`_ROW_ACTIONS` (`admin_brackets.py:83-100`) is exactly four buttons — manage,
results, complete, advance — wired at `:660-663` and reused verbatim for the
mobile card. No pencil, no trash, no row-click handler in 666 lines.
`update_bracket` (`bracket_service.py:155-197`) and `delete_bracket`
(`:239-255`) exist, are DRAFT-gated, audit-logged, and exposed at
`api/routers/brackets.py:178-193`. The page's own docstring advertises the
missing capability: *"author its bracket stages (create/edit/delete while
DRAFT)"* (`admin_brackets.py:4`). The house convention is the opposite —
[`admin_qualifiers.py:108-113`](../../pages/admin_tabs/admin_qualifiers.py#L108)
puts Manage + edit + delete on every row.

Worse: `update_bracket`'s signature is `(actor, bracket_id, name, stage_order,
config)`. **Format is not editable by any surface.** And the resulting deadlock
is total — a wrong-format stage at `stage_order 0` cannot be deleted, cannot be
renamed out of the way, and blocks a replacement at 0 (`bracket_service.py:123-124`).
Creating the correct stage at 1 instead does not help: `start_bracket` refuses
any `stage_order > 0` whose predecessor is not COMPLETE
(`_bracket/generation.py:37-45`). The only in-app path out is enrolling
throwaway entrants into the wrong stage, starting it (which publishes and DMs),
and completing it. `DELETE /brackets/{id}` with a write token is the real answer
— mid-event.

*Softening:* DRAFT stages are staff-only (`theme/brackets/visibility.py:19`), so
a typo'd name is private until Start. The organizer gets a review window; they
just have no tool to act on it.

### P2 — Blocker · Linking an entrant to a user means typing a raw database primary key, and it can never be set afterwards

`admin_brackets.py:201-202` is the entire linking UI:
`ui.number('User ID (optional)', min=1)`. No picker, no search, no name lookup —
against a house convention that is unanimous everywhere else
([`match_dialog.py:443-449`](../../theme/dialog/match_dialog.py#L443),
`checkout_dialog.py:29-37`, `equipment_dialog.py:61` all use
`ui.select({u.id: u.preferred_name}, with_input=True)`). The admin Users table
has no id column ([`admin_users.py:29-35`](../../pages/admin_tabs/admin_users.py#L29)).
The value leaks into the product only through two analytics report URLs.

**There is no repair.** `repository.update_entrant` has exactly one caller —
`drop_entrant`, which writes status only. No service method, REST endpoint, MCP
tool or Discord handler ever sets `user_id` on an existing entrant. Two
docstrings promise otherwise: `models/bracket.py:71-74` ("seed with a
`display_name` now and link a user later — one link fixes the entrant in every
stage") and `_bracket/notifications.py:170-171` ("the DM will fire when the
entrant is linked"). Neither capability was built.

What an unlinked entrant costs: `notify_matchup_ready` returns silently
(`notifications.py:177`), `list_open_matches_for_user` filters the matchup out of
**both** players' dashboards (`_bracket/scheduling.py:36-41`), and
`schedule_bracket_match` hard-raises (`:133`).

*Corrected from the first draft:* the bracket is **not** bricked —
`report_result`, `complete_stage` and `advance_stage` need no link, so staff can
run the whole thing by hand. And staff do eventually get a diagnosis: the
"Schedule game N" button renders regardless of linkage
(`theme/brackets/dialog.py:96-101`) and produces *"Both players must be linked to
schedule this match."* But it arrives after the roster is built and the stage
started, naming a state no screen displays and no control can change. The players
themselves just see silence.

I walked into this without noticing. My 8-entrant bracket started cleanly,
rendered perfectly on the public page, and cannot be scheduled or announced by
anyone.

### P3 — Blocker · Building the field is one-at-a-time typing, with no bridge to the roster the app already collected

`add_entrant` (`admin_brackets.py:199-217`) and per-row `enroll` (`:235-250`)
each end in `await body.refresh()` (`:215`, `:246`), and `body` is one
`@ui.refreshable` wrapping the whole dialog (`:182-188`) that re-runs four
service reads and rebuilds every row. `repository.create_entrant` has exactly one
UI caller and a strictly one-per-call `POST /brackets/entrants`. No paste, no
CSV, no multi-select, no "enroll all". `submit_on_enter` — which `form_dialog`'s
own docstring instructs callers to wire
([`theme/dialog/_helpers.py:16-25`](../../theme/dialog/_helpers.py#L16)) and
which 11 other dialogs use — is absent, so the form is mouse-only.

The rebuild also destroys unsaved work. **Measured firsthand:** type seeds into
three rows on a 32-entrant DRAFT stage, then add one forgotten entrant — all
three seed fields read back empty, because the refresh rebuilds every seed input
from the database.

The sharpest part is the missing bridge. `TournamentPlayers`
([`models/tournament.py:112-123`](../../models/tournament.py#L112)) is populated
by players self-enrolling from their Profile tab, readable via
`TournamentService.get_enrolled_players_by_tournament_id` — and those rows carry
`user_id`, the exact field P2 says cannot otherwise be obtained. Grep for
`TournamentPlayer` across `admin_brackets.py` and `_bracket/` returns nothing.
**One import button would collapse the click count and dissolve the linking
blocker in the same change.**

### P4 — Blocker · A stage entry can never be removed, and `BracketEntryStatus.DROPPED` is written by no code in the product

`BracketRepository` has `create_entry` / `get_entry` / `update_entry` /
`set_entry_seeds` / `list_entries` and **no delete**
(`bracket_repository.py:79-122`). `drop_entrant` exists and is REST-only — never
called from `pages/` or `theme/`.

The deeper hole is documented by the code that has it:
`api/routers/brackets.py:243-246` says the roster drop *"does not cascade into
their per-stage `BracketEntry.status`, which is what stage advancement filters
on, so a drop mid-stage still needs the entry retired separately."* Nothing can
retire it. `BracketEntryStatus.DROPPED` is written in exactly two places
repo-wide — `scripts/seed_brackets.py:243` and a test — both reaching past the
service to set `entry.status` by hand. **The dev fixture had to cheat to produce
a state the product cannot reach**, which is the clearest possible signal that
the authoring path is missing.

Operationally: a no-show on day two of a Swiss event cannot be retired and will
advance into the playoff on their accumulated `final_rank`.

### P5 — Major · You never see the bracket before you commit it, and the commit is the publish, the notification and the point of no return

`start_bracket` writes `state = ACTIVE` (`generation.py:62-63`) and immediately
calls `notify_open_matchups` (`:78`). There is no un-start, and
`delete_bracket` / `update_bracket` / `enroll` / `set_seeds` all refuse
afterwards. `is_visible` returns True for anything non-DRAFT and both bracket
routes are `@public_page`.

The button is `ui.button('Start bracket', icon='play_arrow', on_click=start)`
(`admin_brackets.py:351`) — no confirmation, no tooltip, no copy. The toast is
`'Bracket started'`. Meanwhile `complete_stage` gets a full `ConfirmationDialog`
with excellent copy (`:540-546`) and `advance_stage` gets a named-entrant
preview plus confirm (`:562-585`). **The one strictly unrecoverable action in the
file is the only one with neither.**

And the operator cannot answer the two questions they actually have — is my
1-seed opposite my 2-seed, who gets the byes — because nothing renders a DRAFT
stage. The Results dialog's visual embed is gated on `bracket.format in
_ELIM_FORMATS and bool(matches)` (`:408-412`), and matches exist only after
Start. The public page short-circuits DRAFT to *"This stage has not started
yet."* The engines are pure and could be run in-memory for exactly this;
nothing does.

*Fairness:* Start is not one of the four adjacent 44px row icons — it sits at
the end of the Manage dialog behind four service preconditions, and
`_assign_seeds` refuses an inconsistent seeding rather than committing it. It is
a considered action reached deliberately. It is still the action that publishes
the draw and DMs the field with no statement that it does either.

### P6 — Major · The advancement rule is invisible, uneditable, and silently dead on stage 0

`count` and `per_group` describe the field **leaving** the source stage
(`_compute_advancers(source, advancement)`, `multistage.py:122-163`), but the
blob must be stored on the **destination** stage (`raw = (next_stage.config or
{}).get('advancement')`, `:116`). The label reads correctly; the filing cabinet
is one drawer over. [docs/features/brackets.md](../features/brackets.md) states
this plainly — the UI never does. Its only guidance is the caption
`'Advancement (stage > 0 only)'` (`admin_brackets.py:601`), easy to read as
"which stages can advance" rather than "which stage stores the rule".

Nothing enforces it: `BracketConfig` never receives `stage_order`, so an
`advancement` block typed on stage 0 is accepted, persisted, and read by nobody
— both readers look forward. Then it becomes unverifiable: the table columns are
id/stage/name/format/state and `refresh_table` drops `config` entirely
(`:145-154`). **The Create dialog is the sole writer of these values and admin
has no reader.**

Two sharp edges inside the block, both real:

- `_seed_advancers` **ignores `seeding` entirely unless `per_group` is true**
  (`multistage.py:176`). The dialog defaults Seeding to Snake and Per group to
  off, so the default combination silently discards the selected policy.
- With `per_group` off against a grouped source, `count` is a global cut over
  per-group `final_rank`s. That reproduces top-N-per-group exactly when `count`
  divides evenly by the group count; when it does not (6 from 4 groups) the final
  tier is filled by source seed rather than merit.

### P7 — Major · Four unconditional row actions, two of which can only fail on a DRAFT stage and one of which can essentially never succeed on an elimination stage

`_ROW_ACTIONS` is a static string with no `v-if`, against the house pattern
([`admin_equipment.py:82-85`](../../pages/admin_tabs/admin_equipment.py#L82)
gates on `props.row.status_value`). On a DRAFT row: Results shows "No open
matches."; Advance raises *"The predecessor stage must complete first"* about a
stage the operator was not thinking about; Complete opens the red
irreversible-action modal and **then** fails with *"Only an ACTIVE bracket can be
completed"*.

For SINGLE_ELIM and DOUBLE_ELIM the Complete button has no reachable success
state at all. `_record_result` calls `_maybe_complete_stage` after every result,
which auto-finalizes the instant the final resolves
(`_bracket/completion.py:88-94`); `complete_stage` then rejects both remaining
cases. On the two most common formats the flag icon is a red confirmation
followed by an amber failure, every time — which teaches operators to distrust
the one confirmation dialog in this feature that is telling the truth.

On a phone the same four ~44px targets sit adjacent in the card footer where
`q-tooltip` never fires, so they are unlabelled glyphs and the highest-consequence
one is a thumb-width from the most-used one. The file itself flags this hazard
when justifying the Complete confirmation (`:521-526`).

### P8 — Major · No standings anywhere in admin, and the tie-break the service accepts is unreachable

`complete_stage(actor, bracket_id, tie_breaks=None)` exists specifically so staff
can rule before `final_rank` is written — its own docstring says *"the
staff-triggered finalizer (so staff can review standings and resolve ties
first)"*. **Every caller passes `None`**: the page (`admin_brackets.py:533`),
REST (`api/routers/brackets.py:390-391`), and both automatic paths. The only
non-`None` caller in the repo is a test.

The standings engine computes ties expressly for this — unresolved equals share a
rank and list each other in `tied_with`
([`bracket_engines/standings.py:71-79`](../../application/services/bracket_engines/standings.py#L71)).
`BracketService.standings` is rendered on the public page, REST and MCP — **and
nowhere in Admin → Brackets**, though the renderer already exists
(`theme/brackets/tables.py:37`).

So to finalize a Swiss stage, the organizer clicks a button that writes every
`final_rank` from a points table they have never been shown, on a stage that
cannot be un-completed, feeding a next-stage draw. A tie for the last advancing
slot is unresolvable by any human using any surface of this product.

### P9 — Major · Overriding a result from the flat list silently erases the recorded scores and the forfeit flag

`admin_brackets.py:390-399` calls `service.override_result(actor, match_id,
winner_entry_id)` with no score or forfeit arguments. `override_result` declares
`entry1_score=None, entry2_score=None, forfeit=False` and assigns all three
unconditionally (`_bracket/advancement.py:370-378`, `:423-426`). Scores arrive
automatically on a series clinch, so a raced Bo3 carries 2-1 without anyone
typing it; overriding from the list turns that into a scoreless win and drops the
"FF" marker from the public bracket — with a green "Result overridden" toast.

The card-dialog path preserves them. **For Swiss and round robin the wiping path
is the only override surface in the product**, because the score-preserving
dialog is gated on `_ELIM_FORMATS` in both the admin embed and the public page.

### P10 — Major · Seeding has no tools, accepts duplicates at enroll, and cannot clear a seed

`enroll` takes a seed and applies no uniqueness or range check
(`bracket_service.py:350-392`); there is no DB constraint. The collision surfaces
at Save seeds (*"Seed 3 is assigned to more than one entry"*) or at Start
(*"Bracket seeds must be a contiguous 1..N…"*) — both naming a number, never an
entrant, in a 5-second toast.

`save_seeds` filters blanks out (`if w.value is not None`,
`admin_brackets.py:271`), so the documented `None`-clears contract is unreachable
from the UI: blanking a box appears to work, reports success, and leaves the old
value.

No randomize (grep for `random`/`shuffle` across `_bracket/` and
`bracket_engines/` is empty), no drag-to-reorder (zero `draggable` in `pages/` or
`theme/`), no import from the async-qualifier leaderboard. A qualifier-seeded
event — the standard shape here — means reading a leaderboard in another tab and
transcribing the order by hand.

There is also a timing inversion I hit firsthand: **seed boxes are blank exactly
while they are editable and populated exactly once they are not.** `enroll`
stores `seed=None`; seeds are assigned at Start by `_assign_seeds`, which
gap-fills 1..N in enrollment order. So the whole DRAFT phase shows empty boxes
with no statement of what will happen if they are left alone — then after Start
the numbers appear, "Save seeds" is gone, and the inputs are **still not
disabled**. Typing `99` into one is accepted with nothing that could save it.

### P11 — Moderate · Per-round best-of cannot be set before a stage starts

The round editor is gated on `distinct_rounds` derived from `matches`
(`:295-300`), and matches exist only after Start, so a DRAFT stage cannot be
given a series length in the UI. The Create dialog has no rounds field. Only REST
can author it at create time — which is exactly what `scripts/seed_brackets.py`
does.

*Corrected from the first draft:* entrants are **not** told "Best of 1". Both DM
builders suppress the format line entirely at `best_of <= 1`
(`application/utils/discord_messages.py:251-252`, `discord_embeds.py:155-156`),
and the same suppression is systematic across six surfaces including the game
title. No wrong number is announced and there is nothing to retract. Nor is the
fix lost: `set_round_metadata` is explicitly editable in any state, the panel
appears in the same open dialog immediately after Start, and raising best-of
afterwards opens the extra game slots live.

What is worth fixing is the caption — *"Shown in the public bracket round headers
(best-of must be odd; time is Eastern)"* — which reads as cosmetic while
`RoundConfig` calls `best_of` semantic. **A TO who reads the caption as a label
will ship a Bo1 semifinal.** And the editor labels rounds "Round 1 / Round 2 /
Round 3" while the headers it configures render "Quarterfinals / Semifinals /
Final".

### P12 — Moderate · Format-specific fields render for every format; seven live config knobs have no control at all

`swiss_in` and `groups_in` render unconditionally and `fmt_in` has no
`on_change`. `BracketConfig` has no cross-field validator, so `swiss_rounds` on a
single-elim stage is stored dead, as is `group_count` off round robin.
"(optional)" on each label reinforces the wrong reading.

Going the other way, seven live engine inputs have no widget anywhere in
`pages/`: `grand_final_reset` (consumed at `double_elimination.py:90-108`),
`win_points` / `draw_points` / `loss_points` / `bye_points`, `tiebreakers` and
`omw_floor` — all read by `standings.py:96-107`, which is what ranks a Swiss/RR
stage and therefore decides who advances. A double-elim organizer cannot choose
whether the grand final has a reset; a Swiss organizer is silently committed to
`buchholz, omw, head_to_head`. Since config is DRAFT-only and P1 removed the
editor, both are locked at the Create click.

Related: a blank "Swiss rounds" silently derives `max(1, ceil(log2(N)))`
(`completion.py:204-207`), recomputed from *current active* entrants on every
round advance — so a 20-player Swiss announced as 5 rounds ends after 4 if five
players drop. No surface displays the target before or after.

### P13 — Moderate · The advance preview omits the guard the real advance enforces

`advance_stage` rejects a re-advance; `get_advancing_preview` never checks
`list_entries`, despite its docstring claiming *"Raises the same guards."* The
page previews first and opens the dialog on success, so on an already-advanced
chain the operator gets a confident list of advancers, clicks Advance, gets an
amber toast — and `do_advance` returns before `dialog.close()` (`:577` vs
`:579`), leaving the same dialog open, unchanged, clickable again.

The dialog is titled `f"Advance from stage {from_stage_order}"` — raw 0-based, so
"Advance from stage 0" for what every public surface calls Stage 1 — and lists
`#{final_rank} — {name}` only. `_advancement_context` already resolved the
destination bracket and the rule and `_seed_advancers` already computed each
advancer's resulting seed; none of it reaches the dialog. Snake vs preserve
materially reorders the field and the operator sees no trace of which was
applied.

### P14 — Moderate · The Manage dialog never says what state it is in, and leaves dead controls live

Title is `f"Manage — {row['name']}"` — no state badge, no stage number, though
both are loaded at `:185`. On a started stage the Add-entrant form stays fully
live (`add_entrant` has no state check), but `enroll` is DRAFT-only, so entrants
added after Start become permanent orphans with a bare `disable` prop and no
tooltip. The service is correct in every case — this is purely the UI advertising
what the service forbids.

### P15 — Moderate · The tournament selector is unfiltered, unsearchable, and lists tournaments where creation always fails

`Tournament.filter(tenant_id=tenant_id).order_by('name')` (`:122`) — no
`is_active` filter, no exclusion of Challonge-linked tournaments, no
`with_input=True`. The Challonge conflict is detected only in the service, after
Create is clicked, and the dialog captured `tid` at open, so the operator cannot
change tournament from inside it.

There is also **no migration path**: `ChallongeService` has `unlink_player` but
no `unlink_tournament`, and the tournament edit dialog refuses a blank Challonge
id, so `challonge_tournament_id` can never be cleared. A community moving *off*
Challonge — the stated point of this feature — cannot migrate an existing
tournament at all.

Plus: `state['tournament_id']` starts `None`, the select has no `value`, and the
table has no `no-data` slot (siblings have one). First contact is a blank page
with a dropdown and a button that scolds you.

### P16 — Minor · Creating stage 0 silently switches the tournament to bracket-only scheduling

`create_bracket` does, with no flag and no mention:
`if tournament.allow_player_match_requests and stage_order == 0: …
allow_player_match_requests=False` (`bracket_service.py:136-141`). The toast is
`'Bracket created'`. The design decision is right and the code comment explains
it well — but it rides along with an action that reads as additive, and it
silently removes the tournament from every player's match-request dropdown. The
reverse control exists and explains itself
([`tournament_edit_dialog.py:145-156`](../../theme/dialog/tournament_edit_dialog.py#L145):
*"Turned off automatically when a bracket is attached."*) — on a different tab,
in a dialog the operator did not open.

### P17 — Minor · Vocabulary drift

- **Stage numbering** is raw 0-based in the table (`:149`) and the advance dialog
  (`:562`); both public surfaces render `stage_order + 1`
  (`pages/brackets.py:348`, `pages/home_tabs/brackets.py:47`). An operator taught
  "Stage 1" by the public page types 1 for their first stage, and
  `_advancement_context`'s `from_stage_order + 1` lookup then never finds a
  successor.
- **State** is `b.state.value` — lowercase `draft`/`active`/`complete` in plain
  text — while `format` on the very next line is humanized through
  `FORMAT_OPTIONS`, and `state_color`/`STATE_COLORS` are already exported from
  the same package this file imports from. State is the column that determines
  which of the four buttons will work, rendered as the least scannable thing on
  the row.
- **The results lists print `f'R{m.round} #{m.position}'`.** A losers match reads
  "R-2 #1"; a round-robin group-2 match reads **"R1 #100001"**, because positions
  are offset by group to keep the uniqueness constraint. That is the *primary*
  surface for round robin — there is no visual embed for it — and the dev fixture
  ships `group_count: 2`. Meanwhile the same file's round editor already says
  "Losers Round 2" and the service has full `round_names` producing "Semifinals".
- **The internal row ID is on screen** — `{'name': 'id', …, 'hidden': True}`
  (`:126`) does not hide anything. Repo-wide pattern, not bracket-specific, but
  it is the first column an organizer sees here.

### P18 — Minor / polish

- **No client-side validation anywhere in the Create dialog.** `ui.input('Name')`
  has no `required`, no `validation=`. None of the four `ui.number` fields carries
  `precision=0`, so `3.5` is silently truncated by `int()`. Combined with the
  deferred duplicate-stage and Challonge checks, three failed submits before
  success is a plausible first run. Errors do preserve the form — confirmed
  firsthand.
- **Raw pydantic in a toast.** Type an even Best of and `validate_config_blob`
  stringifies the whole `ValidationError`
  ([`application/utils/config_validation.py:36`](../../application/utils/config_validation.py#L36)):
  *"Invalid bracket config: 1 validation error for BracketConfig / rounds.3.best_of
  / Value error, best_of must be odd … [type=value_error, input_value=2,
  input_type=int] / For further information visit https://errors.pydantic.dev/…"*
  — 268 characters in a 5-second, non-dismissable, single-line toast
  (`theme/notify.py:24-25` passes no `timeout`, `close_button` or `multi_line`).
- **Auto-complete is silent.** The last reported result runs `_finalize_stage` —
  writing every `final_rank` and locking the stage, exactly what the manual button
  warns about at length — and the toast says `'Result recorded'`.
- **Empty states are terminal.** "No entrants yet.", "Nobody enrolled yet." —
  against a house style that routes: *"No tournaments are linked to Challonge yet.
  Link one from its edit dialog on the Tournaments tab."*
  (`admin_challonge.py:82-83`). Sharpest at "Nobody enrolled yet", which is also
  when Start is hidden, with no sentence connecting the two.
- **No link to the bracket from admin.** `admin_brackets.py` contains zero
  `ui.navigate.to` calls, though the browse tab, the schedule table and the match
  dialog all link to `/brackets/{id}`.
- **The roster is unbounded and unsearchable**, lists DROPPED entrants with a live
  Enroll button, and shows everyone twice. The volunteer picker does all three
  correctly (`admin_volunteers.py:214-234`).
- **Staff scheduling loses the availability suggestion.**
  `BracketScheduleDialog._defaults` computes a `MatchSuggestionService` suggestion
  only when `tournament_id` and two `player_ids` are supplied; the staff entry
  point passes neither, though it holds the resolved matchup. Staff scheduling on
  players' behalf get "right now"; the player booking the same matchup gets a real
  suggestion.
- **The dialog action bar sits inside the refreshable** (`:348`), so the
  direct-child-scoped maximized-sheet CSS rule cannot match and on a phone the bar
  reads as a floating strip rather than a footer. The two non-refreshable dialogs
  in the same file get it right.

---

## What is already good — do not change it

This is not a rewrite. Several things here are better than the commercial tools.

- **The service layer is careful and honest.** `_assign_seeds` refuses an
  inconsistent seeding with a message quoting the actual seed list rather than
  silently stranding an engine slot. `set_seeds` validates the whole resulting map
  before any write. `_ensure_no_challonge_link` is symmetric with
  `ChallongeService`. Docstrings state invariants rather than restating code.
- **`advance_stage` is the best-designed step in the feature** — a real named dry
  run rendered as a preview dialog with Cancel, and the next stage lands in DRAFT
  so seeds stay editable before starting. Challonge has no multi-stage at all.
- **`_snake_order` is genuinely sophisticated** (`multistage.py:194-249`),
  guaranteeing no round-1 same-group pairing by working backwards from the
  elimination engine's seed reflections. That is real domain expertise.
- **The Bo1 chrome suppression is a deliberate, systematic convention**, applied
  identically across six surfaces. Two audit passes mistook it for a bug, which is
  a compliment to how invisible it is.
- **DRAFT invisibility is pure, shared and unit-testable**
  (`theme/brackets/visibility.py`) — one rule, three consumers, no duplicated
  filters. This is precisely the substrate a preview/publish flow needs.
- **Click-a-card result reporting** — the shared renderer embedded in the Results
  dialog with the flat lists kept as an explicit fallback — is Challonge-grade,
  and the reasoning for the fallback is written down.
- **The mobile work is real, not theoretical.** The comments record measured
  problems: "'Start bracket' and 'Close' ~1200-4400px below the fold",
  `col min-w-0 ellipsis` because long names pushed Enroll onto a second line,
  collapsed fallback lists so a 32-match stage does not bury the actions under
  ~3000px. Someone used this on a phone.
- **Per-round metadata is editable in any state** — start.gg parity, ahead of
  Challonge.
- **The Complete confirmation's copy is exactly right**: *"This writes every
  entrant's final rank and locks the stage — it cannot be undone."* That sentence
  is the model for the one Start needs.

---

## Remediation, in three waves

### Wave 1 — Make mistakes survivable (small effort, removes every blocker's sharpest edge)

> **Status: shipped.** All ten items are implemented; the page is now the package
> `pages/admin_tabs/admin_brackets/` (it crossed the 800-line budget mid-change).
> Two deliberate departures from the plan below, both narrowing it:
>
> - **Item 8** filters Challonge-linked tournaments out of the selector but keeps
>   inactive ones (sorted last, suffixed `(inactive)`). Filtering on `is_active`
>   would have made an old tournament's existing stages unreachable — the finding
>   was clutter, and the fix should not cost access.
> - **Item 9** disables the seeding controls outside DRAFT but leaves the
>   Add-entrant form live. Adding to the roster genuinely works in any state
>   (`add_entrant` has no state check) and is useful for a later stage; only
>   *enrollment* and *seeding* are DRAFT-only, and those are what is now disabled,
>   under a caption that says so.
>
> Two things came along because the change made them cheap and their absence was
> a live defect: the roster import and the entrant link are exposed over REST too
> (`POST /brackets/entrants/import`, `PATCH /brackets/entrants/{id}/user`) rather
> than being UI-only, and `scripts/seed_dev.py` now seeds a DRAFT stage — without
> one, every new control in this wave was invisible to the browser-validation
> loop and to anyone running the dev app.

1. **Edit + Delete row actions**, `v-if`-gated on `props.row.state === 'draft'`
   (P1). Refactor `open_create()` into `open_form(existing=None)` prefilling from
   the row and calling `update_bracket`; route delete through the
   `ConfirmationDialog` already imported at `:42`. Copy
   `admin_qualifiers.py:108-113`. Both service methods and both REST routes
   already exist and are DRAFT-gated — this is pure wiring.
2. **Allow `format` in `update_bracket` while DRAFT** (P1). A DRAFT stage has no
   match graph; nothing is invalidated. One parameter, one `update_data` key.
3. **Replace the User ID number box with the house picker, and add
   `BracketService.set_entrant_user`** (P2). The repository's `update_entrant`
   already exists, so the service method is ~15 lines. Add a `link`/`link_off`
   icon per roster row so unlinked entrants are visible at a glance.
4. **"Import from tournament roster" button** (P3, P2). One call to
   `TournamentService.get_enrolled_players_by_tournament_id`, `add_entrant` per
   row with `user_id` already attached, one refresh. **The single
   highest-leverage change in this audit** — it collapses the click count *and*
   eliminates the linking blocker as a side effect.
5. **`ConfirmationDialog` on Start** (P5), in the voice of the Complete one:
   *"Start "Round 1"? This generates the match graph from the current seeding,
   publishes the stage publicly, and DMs N entrants their opening matchup. Seeds
   cannot be changed and the stage cannot be deleted afterwards."*
6. **State-gate the four row actions** (P7): manage on draft/active, results on
   active/complete, complete only when completable (never on elimination —
   replace with a static "auto-completes on the final" hint), advance only on
   complete with a successor. `admin_equipment.py:82-85` is the template.
7. **Pass the match's current scores/forfeit through the flat-list override**
   (P9) — a three-argument change at `:393` that stops the data loss until the
   dialog unification in Wave 2.
8. **Filter and search the tournament selector** (P15): `is_active=True,
   challonge_tournament_id__isnull=True`, plus `with_input=True`; default it when
   there is exactly one; add a `no-data` slot.
9. **Disable what does not work** (P14): seed inputs and the Add-entrant form
   when `not is_draft`, with one caption; state + stage in the Manage dialog
   title.
10. **Default `stage_in` to `max(existing stage_orders) + 1`**, label it "Stage
    order (0 = first stage)" (P17), add `precision=0` to the four number fields,
    and wire `submit_on_enter` per the `form_dialog` contract (P18).

*Makes possible:* an organizer can be wrong. Every authoring decision becomes
reversible while DRAFT, the roster can be built in one click from data the app
already has, every entrant is linked by default, and the one-way action announces
itself. This alone removes most of the clunky feeling, because clunky is mostly
*fear of an irreversible form*.

### Wave 2 — Make the flow verifiable (medium effort, removes the guessing)

> **Status: shipped.** All seven items are implemented. Three notes where the plan
> turned out to be wrong or incomplete:
>
> - **Item 12** claimed "no service change required". It needed one:
>   `tie_breaks` was honoured in `_rank_swiss` only, so on round robin — where the
>   cut line is *per group* and therefore tightest — a staff ruling was silently
>   inert. `_rank_round_robin` now applies it too.
> - **Item 11** is backed by a real service method (`preview_draw`) rather than
>   presentation code calling the engine: the seeding rule and the bye
>   materialization are business logic, and a preview that reimplemented them
>   would drift from the Start it is meant to rehearse. A test asserts the
>   projected graph equals the persisted one.
> - **Item 17** also revealed that the *table* was offering Advance on a chain
>   whose successor had already started. `can_advance` now checks every guard the
>   advance enforces, not just that a successor exists.


11. **Draw preview for a DRAFT stage** (P5). Run
    `get_bracket_engine(fmt)().generate(len(entries), config)` in-memory over the
    current seeding, map each `GeneratedMatch` to an unsaved `BracketMatch` with
    synthetic ids, and feed the existing `build_context` / `render_elimination`
    with `on_card_click=None`. Text preview for Swiss/RR ("N rounds", "G groups of
    K"). Refresh when seeds change.
12. **Standings + tie-breaks in the admin surface** (P8). Render
    `service.standings(bracket_id)` through the existing
    `theme/brackets/tables.render_standings` at the top of the Results dialog for
    non-elimination formats; on Complete, show the table with `tied_with` rows
    highlighted and a rank input each, and pass the collected `{entry_id: rank}`
    into the `tie_breaks` argument the service has always accepted. **No service
    change required.**
13. **`unenroll` + `retire_entry`** (P4). `BracketRepository.delete_entry` plus a
    DRAFT-only `unenroll`, and `retire_entry` writing `BracketEntryStatus.DROPPED`
    in any state (audited, evented). Surface both as row buttons in Manage, plus
    `drop_entrant` on the roster. Delete the seed script's hand-written
    `entry.status` write — that it exists is the bug report.
14. **Config readout** (P6, P12). A `_config_summary(bracket)` helper next to
    `FORMAT_OPTIONS` rendering "Swiss · 5 rounds", "Round robin · 4 groups",
    "Draws top 2 per group from stage 0 (snake)" — as a table sub-line, reused on
    the public stage index. Relabel the advancement block to name the direction,
    hide it when `stage_order == 0`, and reject an `advancement` key on stage 0 in
    `create_bracket`.
15. **Best-of before Start** (P11). Either add `default_best_of` to
    `BracketConfig` consulted by `resolve_best_of` between the per-round value and
    the `1` fallback, or render the round editor for DRAFT against the engine's
    *predicted* round list. Fix the caption to state the semantics and reconcile
    the two contradicting docstrings.
16. **Unify the override path** (P9). Route the flat-list rows through
    `build_match_dialog`, which gives Swiss and round robin score and forfeit
    entry for the first time.
17. **Move the already-seeded check into `_advancement_context`** so preview and
    write share it (P13); render the already-seeded case as informational; close
    the dialog on terminal errors; title it with both stage names and show
    `seed → name (was #rank, Group N)` from the tuples `_seed_advancers` already
    returns.

*Makes possible:* the organizer can answer "does this look right?" before
committing, "who actually won the group?" before finalizing, and "what did I
configure?" at any time. The feature stops being a form you submit into the dark.

### Wave 3 — Make it teach (larger or lower-frequency)

> **Status: shipped.** All seven items are implemented. Decisions worth recording:
>
> - **Item 18** could not be a pydantic `model_validator`: `BracketConfig` never
>   sees the format it belongs to. `validate_bracket_config(config, fmt=,
>   stage_order=)` carries the cross-field checks instead, so REST is covered by
>   the same guard as the UI. A key sitting at its schema *default* is tolerated —
>   the normalizer injects every non-None default, so a stage's own stored blob is
>   re-submitted carrying keys nobody typed, and rejecting those would make every
>   edit fail.
> - **Item 20** took the `CANCELLED` route rather than the ACTIVE→DRAFT reset: the
>   finding was about *abandonment*, and a reset erases the fact that the stage was
>   ever run. A cancelled stage keeps its played results, is hidden from the public
>   views by `is_visible`, cannot be advanced out of, and can be deleted — which
>   returns the `stage_order` slot a replacement needs.
> - **Item 24**'s overflow menu replaced the row's icon strip entirely rather than
>   demoting "the remaining actions": with a computed primary button, an icon that
>   is sometimes present and sometimes not is harder to aim at than a menu that is
>   always in the same place — which was half of P7's phone complaint.
> - **Item 19**'s "Seed from qualifier" is gated on the `ASYNC_QUALIFIERS` flag
>   being live, since it calls a flag-gated service.


18. **Format-reactive Create dialog + the unexposed knobs** (P12). Bind an
    `@ui.refreshable` panel to `fmt_in`; double-elim gets `grand_final_reset`;
    Swiss/RR get a tiebreaker-order multi-select over `KNOWN_TIEBREAKERS` and the
    four point values behind a nested "Scoring" sub-expansion. Add a
    `model_validator` rejecting `swiss_rounds` off Swiss and `group_count` off
    round robin so REST cannot store dead keys either.
19. **Seeding toolbar** (P10): "Number 1..N as listed", "Shuffle", "Reverse", and
    "Seed from qualifier" (a select of closed qualifiers → `get_leaderboard` →
    match `user_id` → rank order, reporting unmatched names rather than guessing).
    All write through the existing `set_seeds`. Submit `None` for a blanked box;
    name entrants in the collision error; validate duplicates client-side.
20. **Cancel / abandon an ACTIVE stage.** No in-app close-out exists today —
    either a fourth `BracketState.CANCELLED` hidden by `is_visible` and skipped by
    `_advancement_context`, or an ACTIVE→DRAFT reset that deletes the generated
    matches after refusing when any game is COMPLETE. Today the only close-out is
    fabricating winners for every remaining match.
21. **Challonge migration** (P15). `ChallongeService.unlink_tournament(actor,
    tournament_id)`, audited, with a button on the Challonge tab — so moving off
    Challonge onto native brackets, the stated purpose of the feature, is a
    supported move instead of a duplicate tournament.
22. **Vocabulary pass** (P17). Import `round_label` and `state_color` (already
    exported from `theme.brackets`, a module this file already imports from) and
    use them in the results list, the round editor and a `body-cell-state` badge
    slot; render `stage_order + 1` everywhere; never print the group-offset
    position — say "Group B · Round 1 — Alice vs Bob".
23. **Copy pass** (P18, RC5). Route the blurb instead of narrating it; give every
    empty state a next step; add visible labels under the mobile card icons;
    caption the roster split and the user link; render `validate_config_blob`'s
    pydantic errors as "Round 3: best-of must be odd" and give `notify_error` a
    `multi_line` + `close_button` for long messages.
24. **Table readiness data** (P7, RC3): an entrant/seeded count column and a
    single computed "next step" per row — "Seed & start (0/16 enrolled)", "7/15
    reported", "Ready to complete", "Advance into Playoffs", "Done — Alice" — with
    the remaining actions demoted to an overflow menu. Remember the selected
    tournament in `app.storage.user`.

*Makes possible:* a first-time TO gets from an empty page to a running bracket
without reading [docs/features/brackets.md](../features/brackets.md), and every
rules decision their community argues about (reset, tiebreaker order, round
count, series length) is theirs to set inside the app.
