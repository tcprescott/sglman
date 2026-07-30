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
| [crew-signup-ux.md](crew-signup-ux.md) | Commentator/tracker signup → approval → acknowledge → withdrawal | A pending signup is communicated to staff by text colour alone; the report that can find it cannot act on it |
| [async-qualifier-run-ux.md](async-qualifier-run-ux.md) | A competitor's run, and the review of it | Forfeit is one unconfirmed click and its remedy (`reattempt_run`) is wired to nothing; claimed times are never compared to the server's own clock |
| [new-tenant-onboarding-ux.md](new-tenant-onboarding-ux.md) | Day one for a new community | The first screen is the one action that cannot yet succeed; a new community's Users tab lists every user on the platform |
| [admin-reports-ux.md](admin-reports-ux.md) | Nine report surfaces and their shell | Zero buttons and zero links in any table row across all nine — they identify work and cannot act on it |
| [identity-linking-ux.md](identity-linking-ux.md) | Challonge / Twitch / racetime linking | Four written failure messages, none of which reach the screen (partly code-read — no provider credentials in dev) |

Shipped and deleted: the proctor workflow audit (PR #145 → #146) — its findings
became the proctor board, the review queue, the dispute flag and the station pool.
The equipment lending audit — its findings became the offline banner and the
socket guard, the labelled mobile cards, the guidance line under an actionless
asset page, the bounded loan history, the per-community borrower/owner pickers,
and the encoded-host check on the label sheet.
The volunteer-hub audit — its findings became the draft/publish split
(`auto_generated=True` now means nobody has been told), the `DraftPolicy` that
makes availability a constraint and hours a ceiling, the volunteer's own
release/brief on My Shifts, and the coordinator's coverage strip.

## Cross-cutting themes

Findings that recur across the audits, worth fixing once rather than nine times:

- **One boolean for several capabilities.** `can_crud` on the match board
  ([match-ops RC1](match-operations-ux.md#rc1--can_crud-is-one-boolean-standing-in-for-six-capabilities))
  hides the crew coordinator's approval link and offers them 37 lifecycle controls
  the services refuse. The services' own gates are correct and more granular than
  the UI's.
- **Notification is one-directional** — *half fixed.* Assignment/approval DMs the
  person; the reverse transitions were silent to everyone
  ([crew RC3](crew-signup-ux.md#rc3--notification-is-one-directional)). The
  volunteer half now speaks in both directions: un-assignment and a moved shift DM
  the volunteer, a volunteer's release DMs the coordinators, and a cleared draft
  stays silent on purpose because its creation was. **Crew withdrawal and crew
  un-approval are still silent** — the same fix, not yet applied, and
  `VolunteerScheduleService`'s notification matrix is the worked example.
- **Discovery and action live on different pages.** Reports can see pending crew,
  understaffed shifts and over-capacity peaks; none of them link to the surface that
  fixes it ([reports F1](admin-reports-ux.md#f1--major--nine-reports-zero-actions)).
- **Capabilities nobody wired are invisible.** `reattempt_run`, `review_run`'s
  `note`, `update_bracket`, `state_readonly_slot()` — each exists, is tested, and is
  reachable from no surface.
- **The global `User` table leaks into per-community pickers.** The Users tab and
  the match dialog's "Choose any players" still offer every user on the platform,
  `System` included
  ([onboarding F2](new-tenant-onboarding-ux.md#f2--critical--a-brand-new-communitys-users-tab-lists-every-user-on-the-platform)).
  The equipment borrower and owner selects were the first to be fixed;
  `UserService.get_community_people` is the read the other two want next.
- **The dev seed cannot produce the roles that expose the worst bugs.** A
  coordinator-only or stream-manager-only user has to be granted by hand; three
  audits needed one
  ([match-ops F9](match-operations-ux.md#f9--minor--the-dev-seed-cannot-reproduce-the-two-role-failures-above)).
  The equipment-manager-only case now seeds (`equip_manager`).
- **Confirmation is spent on the reversible actions.** Crew signup gets a modal;
  forfeiting a qualifier run, revoking an approval and arming five lifecycle-clear
  buttons get none.

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
