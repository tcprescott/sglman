# UX evaluations (`docs/reviews/`)

Point-in-time audits of a user-facing flow, each driven against the running app.
Per the [docs conventions](../README.md#conventions-for-this-directory) every file
here is **transient**: delete it once its findings ship — the feature docs become
the truth and git history keeps the rationale.

## The audits

| Evaluation | Scope | Headline finding |
|---|---|---|
| [bracket-creation-ux.md](bracket-creation-ux.md) | Authoring a native bracket stage | The page is a thin RPC console over two-thirds of `BracketService`; ~39 interactions for an 8-player stage |
| [match-operations-ux.md](match-operations-ux.md) | Admin Schedule board + match dialog, across five roles | Four service-level authorization gates compressed into one `can_crud` boolean: a crew coordinator gets 37 controls that all refuse |
| [crew-signup-ux.md](crew-signup-ux.md) | Commentator/tracker signup → approval → acknowledge → withdrawal | A pending signup is communicated to staff by text colour alone; the report that can find it cannot act on it. **Wave 1 shipped** — RC3/F3/F4/F8/F9 closed and F6 halved; F1, F2, F5 and the demand model (RC2) remain |

Shipped and deleted: the proctor workflow audit (PR #145 → #146) — its findings
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

- **One boolean for several capabilities.** `can_crud` on the match board
  ([match-ops RC1](match-operations-ux.md#rc1--can_crud-is-one-boolean-standing-in-for-six-capabilities))
  hides the crew coordinator's approval link and offers them 37 lifecycle controls
  the services refuse. The services' own gates are correct and more granular than
  the UI's.
- **Notification is one-directional** — *discharged.* Assignment/approval DMs the
  person; the reverse transitions were silent to everyone
  ([crew RC3](crew-signup-ux.md#rc3--notification-is-one-directional--closed)).
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
  ([crew F4](crew-signup-ux.md#f4--major--every-message-names-a-database-id-not-a-match--fixed)).
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
  ([match-ops F9](match-operations-ux.md#f9--minor--the-dev-seed-cannot-reproduce-the-two-role-failures-above)).
  Three of those now seed — `equip_manager` (EQUIPMENT_MANAGER only), `vc_user`
  (VOLUNTEER_COORDINATOR only) and `cc_user` (crew coordinator, no role row at
  all) — but a stream-manager-only user still does not.
- **Confirmation is spent on the reversible actions.** Crew signup gets a modal;
  arming five lifecycle-clear buttons gets none. (The qualifier forfeit was the
  worst case and now confirms; so do revoking a crew approval and withdrawing an
  approved commitment, each with copy naming what the other party will be told.)

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
