# UX evaluations (`docs/reviews/`)

Point-in-time audits of a user-facing flow, each driven against the running app.
Per the [docs conventions](../README.md#conventions-for-this-directory) every file
here is **transient**: delete it once its findings ship — the feature docs become
the truth and git history keeps the rationale.

## The audits

| Evaluation | Scope | Headline finding |
|---|---|---|
| [bracket-creation-ux.md](bracket-creation-ux.md) | Authoring a native bracket stage | The page is a thin RPC console over two-thirds of `BracketService`; ~39 interactions for an 8-player stage |
| [sahasrahbot-lessons.md](sahasrahbot-lessons.md) | Wizzrobe vs the maintainer's seven-year-old production race bot | Seed generation has no timeout, retry or provenance — the one contract SahasrahBot wrote down after paying for it |
| [admin-toolbar-ux.md](admin-toolbar-ux.md) | The admin tabs no earlier audit covered (Online play, Webhooks, Discord, Feedback, Service Health, System Config) | Eleven of fifteen Refresh buttons did nothing, silently — and SpeedGaming could not be configured at all |

Shipped and deleted: the match-operations audit — its findings became
`MatchBoardAccess` (one field per service gate, replacing the `can_crud`
boolean), the STREAM_MANAGER's Schedule tab and the TA/CC-scoped board, the
edit dialog's state strip and honest acknowledgment copy, the SpeedGaming
sync's reconciled acknowledgment rows, the labelled and reversible rewind
buttons, the schedulable-tournaments list with its entrant counts, the
optimistic lock's two named exits, the Day filter, the shared read-only state
cell, and `match_model_label` for the dialogs that still quoted an id.
The crew-signup audit — its findings became the crew coordinator's approval
link, the board's pending-crew strip, the conflict check behind an approval,
the per-role coverage shortfall on every row, and **My Crew** on Home (the
volunteer's own list, modelled on My Shifts).
The proctor workflow audit (PR #145 → #146) — its findings
became the proctor board, the review queue, the dispute flag and the station pool.
The equipment lending audit — its findings became the offline banner and the
socket guard, the labelled mobile cards, the guidance line under an actionless
asset page, the bounded loan history, the per-community borrower/owner pickers,
and the encoded-host check on the label sheet.
The identity-linking audit — its findings became `theme/notice.py`, the Challonge
callback's four named outcomes, the collision pre-check, and the Connected
accounts card that finally renders the copy it was configured with.
The async-qualifier run audit — four waves closed all seven findings: the confirmed
forfeit and strict `H:MM:SS` entry, `measured_seconds` and the claimed-vs-measured
check, the required rejection reason with both reattempt paths, and the explained
score/estimate with per-reason run availability.
The volunteer-hub audit — its findings became the draft/publish split
(`auto_generated=True` now means nobody has been told), the `DraftPolicy` that
makes availability a constraint and hours a ceiling, the volunteer's own
release/brief on My Shifts, and the coordinator's coverage strip.
The new-tenant-onboarding audit — four waves: the first-admin grant on
`/platform` and the derived setup checklist, `TenantMembership` made real and
every person picker scoped to it, enrolment given a home on the tournament, and
the membership gate with the join door beside it.
The admin-reports audit — its findings became the per-row route out of every
report that names work (and the `?match_id=` / `?day=` params the destinations
grew to receive it), the scroll position that survives a filter change, and the
`FeatureFlag.VOLUNTEERS` gate the Volunteer Coverage report was the last entry
surface to ignore.

## Cross-cutting themes

Findings that recur across the audits, worth fixing once rather than nine times:

- **One boolean for several capabilities.** *Discharged.* `can_crud` on the
  match board hid the crew coordinator's approval link and offered them 37
  lifecycle controls the services refused, while the STREAM_MANAGER — the role
  `assign_stage` names in its own docstring — had no surface at all. The
  services' gates were correct and more granular than the UI's throughout, which
  is the shape of the fix: [`match_access.py`](../../theme/tables/match_access.py)
  carries one field per gate, `test_every_capability_matches_the_service_gate`
  pins each field to the `AuthService` predicate that decides the same question,
  and the slot templates branch on `__RUN__`/`__CONFIRM__`/`__CREW__`/`__STREAM__`
  where they shared one `__CC__`. Worth copying: when a surface and a service
  disagree about who may act, the service is usually right — derive the surface
  from it rather than restating it.
- **Notification is one-directional** — *discharged.* Assignment/approval DMs the
  person; the reverse transitions were silent to everyone
  (crew RC3).
  Both halves now speak in both directions. Volunteers: un-assignment and a moved
  shift DM the volunteer, a release DMs the coordinators. Crew: un-approval DMs
  the crew member, and withdrawing an *approved* commitment DMs the tournament's
  crew owners with the hours of notice they have. The shape that recurs in both
  is worth copying — the *creation* of a thing decides whether its removal is
  worth announcing, which is why an unapproved crew withdrawal and a cleared
  volunteer draft stay silent on purpose.
- **Capabilities nobody wired are invisible.** `update_bracket`,
  `state_readonly_slot()` — each exists, is tested, and is reachable from no
  surface. (`reattempt_run` and `review_run`'s `note` were the same finding and are
  now wired, which is what the fix for it looks like. `TenantService.bootstrap_staff`
  was the costliest instance — the only way to give a new community its first
  admin, wired to nothing — and now has a button on `/platform`.) `LinkSectionConfig`'s
  `description` and `link_button_label` were the same thing in config form —
  declared, populated three times, read by nothing, and praised by an audit that
  had only read the source. Now fixed, with
  `test_every_link_section_config_field_is_rendered` as the guard; that test is
  the shape worth copying elsewhere.
- **Copy that names the database, not the thing.** Every crew, acknowledgment and
  watch string on the schedule board quoted a primary key — *"sign up as a
  commentator for match ID 17"* — while the DM built by the same service named the
  players, the time and the stage
  (crew F4).
  The rule already existed, written down in `discord_messages`' module docstring;
  only one of the two surfaces had read it. Fixed by
  [`match_labels.py`](../../application/utils/match_labels.py), which both now
  share. Worth grepping for elsewhere: an id in a sentence is a defect wherever
  a user can read it.

- **A message written is not a message delivered.** Twenty-one failure strings
  across the linking and login pages were queued with `ui.notify` and then
  discarded by the `ui.navigate.to` on the next line — every one of them written
  with care, none of them ever on a screen. Reviewing copy in the source says
  nothing about whether a user sees it; probe the path. Fixed by
  [`theme/notice.py`](../../theme/notice.py), and
  `test_no_link_page_notifies_immediately_before_navigating` keeps the shape from
  coming back.
- **The global `User` table leaks into per-community pickers.** *Discharged.*
  Every per-community picker — the Users tab, the match dialog's players/
  commentators/trackers, bracket entrants, the equipment borrower and owner —
  plus `GET /users` and the MCP `list_users` tool now read
  `UserService.get_community_people`, and
  `test_every_person_picker_is_member_scoped` blocks a new caller of the global
  list. Two allowlisted exceptions remain, both deliberate and both labelled on
  screen: `/platform`'s first-admin dialog (a super-admin choosing from every
  account, precisely because the target community has none yet) and the checkout
  dialog's **Include people outside this community** toggle (the venue case —
  lending to someone who just walked in).
- **The dev seed cannot produce the roles that expose the worst bugs.** A
  coordinator-only or stream-manager-only user has to be granted by hand; three
  audits needed one
  (match-ops F9). *Discharged:* `seed_support.USER_SPECS` now holds one user per
  per-tenant role and nothing else — `cc_user`, `sm_only`, `equip_manager`,
  `vc_user`, `proctor_only` and the rest — and `tests/test_seed_coverage.py`
  fails when a new `Role` arrives without a holder. Both role failures the
  match-ops audit had to grant by hand are reproducible from a plain seed.
- **Confirmation is spent on the reversible actions.** *Discharged.* Crew signup
  got a modal while arming five lifecycle-clear buttons got none. The qualifier
  forfeit was the worst case and now confirms; so do revoking a crew approval and
  withdrawing an approved commitment, each naming what the other party will be
  told. The five rewind buttons now say what they do, toggle instead of arming
  one-way, and summarise at Save what they are about to undo.

- **A control that fails silently is worse than one that fails loudly, and the
  screen cannot tell you which you have.** Eleven of the fifteen admin Refresh
  buttons were dead: a task spawned from a *click* has neither the tenant
  contextvar nor the client stash, so the first scoped read inside raises and
  NiceGUI swallows it. Every one of them rendered, enabled, and did nothing. The
  errors reaching the log were the reverse of helpful — a staff member's click
  logged *"Only Staff can view webhooks"*, and a community with the feature on
  logged *"SpeedGaming … is not enabled for this community"*, because the actor
  and the flags both resolve against no tenant. The method that finds this is
  reading the **server log across a click**, not screenshotting the page; a
  screenshot sweep passes all eleven. `refresh_button` and
  `test_no_tab_hand_rolls_a_refresh_button` close it
  ([admin-toolbar](admin-toolbar-ux.md#1-a-refresh-button-spawned-from-a-click-loses-its-tenant-11-of-15-tabs)).
  The generalisation is worth more than the fix: **once you find a broken
  wiring shape, click every other instance of it before you stop.** Doing that
  turned up My Crew's `acknowledge` and `withdraw`, which read `context.client`
  from *inside* the task — where it raises — so a volunteer's Confirm and
  Withdraw had never worked from the page built to give them one.
- **A convention only half the app honours.** `{'hidden': True}` on a column is
  this repo's own invention. The mobile-card renderer honoured it; Quasar, which
  has no such property, painted the column anyway — so seven admin tables led
  with a primary key on desktop and hid it correctly on a phone. Worth
  generalising: when you invent a flag that a third-party component is also
  expected to read, prove the third party reads it. The fix made the convention
  real (`apply_column_visibility` → `visible-columns`) rather than deleting it.

- **An arming mechanism needs every one of its halves.** The five Clear buttons
  set a flag and greyed themselves out: no label saying they roll a match's
  lifecycle backwards, no way to un-arm short of closing the dialog and losing
  every other edit, and no summary at Save. The optimistic lock had the same
  shape from the other end — a correct refusal with no reload, discard or
  overwrite anywhere in the dialog, repeating forever. Both are now
  *decisions with named exits*. Worth grepping for: a control that changes
  nothing on screen but changes what Save will do.

## Method

Every audit here used the same loop, and a new one should too:

1. **Read the services and the auth gates first**, not the page. Most findings are a
   mismatch between what a service permits and what the surface offers.
2. **Boot and seed** — `bash scripts/setup_env.sh`, `./start.sh dev`,
   `poetry run python scripts/seed_dev.py`. See the
   [`ui-validation`](../development.md) skill.
3. **Drive the real app** with a one-off Playwright script (the stock
   `scripts/ui_smoke.js` does login → visit → screenshot; multi-step flows need
   their own script that reuses its login). Count interactions, measure card and
   dialog scroll heights against the viewport, and capture notification copy
   verbatim.
4. **Drive it as every role the surface admits**, not just the one that works. Three
   audits found their headline this way; each needed a role the dev seed does not
   create.
5. **Watch both sides of a transition at once.** Two browser contexts — the
   coordinator and the volunteer, the runner and the reviewer — is what turned
   "drafts exist" into a blocker.
6. **Probe the error paths on purpose**: required fields, empty option lists,
   concurrent edits, permission refusals, junk input, and a forced offline interval
   mid-action.
7. **Re-measure at 390×844.** Mobile is where the row/card ratio turns into
   screenfuls.
8. **Quote measurements, not impressions**, and **tag anything not driven as
   `code-read`.** "1,008 px in an 846 px card" survives review; "the dialog feels
   cramped" does not.
