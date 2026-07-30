# UX evaluations (`docs/reviews/`)

Point-in-time audits of a user-facing flow, and briefs for the ones not yet run.
Per the [docs conventions](../README.md#conventions-for-this-directory) every file
here is **transient**: delete it once its work ships — the feature docs become the
truth and git history keeps the rationale.

## Completed

Each was driven against the running app; the numbers in them are measured, not
estimated.

| Evaluation | Scope | Status |
|---|---|---|
| [bracket-creation-ux.md](bracket-creation-ux.md) | Authoring a native bracket stage: Admin → Brackets, its Create and Manage dialogs | findings open |
| [match-operations-ux.md](match-operations-ux.md) | Admin Schedule board + match dialog; role gating across STAFF / TA / crew coordinator / stream manager / proctor | findings open |
| [crew-signup-ux.md](crew-signup-ux.md) | The commentator/tracker loop: signup → approval → acknowledge → withdrawal, both parties | findings open |

Shipped and deleted: the proctor workflow audit (PR #145 → #146) — its findings
became the proctor board, the review queue, the dispute flag and the station pool.

## Planned (`planned/`)

Briefs, in the order recommended. Each one names its scope, the files, what to
measure, and the leads worth probing — enough for another agent to pick it up
cold. A brief's "leads" are **unverified suspicions from reading the code**, never
findings; the audit's job is to confirm or refute each one against the running app.

| Brief | Why it is worth doing |
|---|---|
| [planned/volunteer-hub-ux.md](planned/volunteer-hub-ux.md) | The admin side is ~625 lines, the volunteer's own side is ~186 — and `/volunteer` is the second-most-visited path in production |
| [planned/async-qualifier-run-ux.md](planned/async-qualifier-run-ux.md) | The only irreversible participant action in the product: one permalink, one clock, Submit or Forfeit |
| [planned/new-tenant-onboarding-ux.md](planned/new-tenant-onboarding-ux.md) | Nobody has ever looked at day one for a new community: every tab empty, every flag off |
| [planned/equipment-live-event-ux.md](planned/equipment-live-event-ux.md) | Phone-in-hand, venue wifi, someone waiting — the flow where emulated-only mobile testing matters most |
| [planned/admin-reports-ux.md](planned/admin-reports-ux.md) | Eight report pages sharing one shell, with a known deferred full-page-reload issue |
| [planned/identity-linking-ux.md](planned/identity-linking-ux.md) | One 484-line shared OAuth flow behind Challonge, Twitch and racetime; the happy path works, the failure paths are unexamined |

## Method

All three completed audits used the same loop, and a new one should too:

1. **Read the services and the auth gates first**, not the page. Most findings are
   a mismatch between what a service permits and what the surface offers.
2. **Boot and seed** — `bash scripts/setup_env.sh`, `./start.sh dev`,
   `poetry run python scripts/seed_dev.py`. See the
   [`ui-validation`](../development.md) skill.
3. **Drive the real app** with a one-off Playwright script (the stock
   `scripts/ui_smoke.js` does login → visit → screenshot; multi-step flows need
   their own script that reuses its login). Count interactions, measure card and
   dialog scroll heights against the viewport, and capture notification copy
   verbatim.
4. **Drive it as every role the surface admits**, not just the one that works.
   Two of the three audits found their headline this way; both needed a role the
   dev seed does not create.
5. **Probe the error paths on purpose** — required fields, empty option lists,
   concurrent edits, permission refusals, states where the action cannot apply.
6. **Re-measure at 390×844.** Mobile is where the row/card ratio turns into
   screenfuls.
7. **Quote measurements, not impressions.** "1,008 px in an 846 px card" survives
   review; "the dialog feels cramped" does not.
