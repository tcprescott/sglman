---
name: ux-audit
description: >-
  Audit one user-facing flow end to end against the running app and write the
  finding up in docs/reviews/. This is the repo's most-repeated workflow —
  sixteen completed audits, whose findings became MatchBoardAccess, theme/notice.py,
  UserTablePreference and the check_table_prefs guardrail, match_labels.py and
  the shared refresh_button — and the only one with no skill. Use when asked to
  audit, review or evaluate a flow, page, role or subsystem from the user's side,
  or to check whether a surface actually offers what its services allow. Broader
  than /ui-validation, which confirms one change renders; this drives every role
  through a whole flow and reads the service gates behind it.
---

# Auditing a user-facing flow

## The one habit that separates this from a screenshot sweep

**Read the server log across each click.** Eleven of fifteen admin Refresh
buttons were dead — bound to nothing, no error, no network call — and a
screenshot sweep passes all eleven, because a button that does nothing looks
exactly like a button that worked. `tail -f /tmp/app.log` in a second shell and
watch what a click produces. Silence is a finding.

## Order of work

Read the gates **before** the page. Most findings are a surface disagreeing with
the service behind it, and the service is almost always right.

1. **Build the capability matrix first.** For the flow's subsystem, list every
   `AuthService` predicate and every service method's own refusal, then every
   control the surface offers. Two columns; the mismatches are the audit. `can_crud`
   on the match board was one boolean standing in for several capabilities: it hid
   the crew coordinator's approval link and offered them 37 lifecycle controls the
   services refused, while STREAM_MANAGER — named in `assign_stage`'s own docstring
   — had no surface at all.
2. **Look for capabilities wired to nothing.** Grep each public service method for
   a caller outside tests. `update_bracket`, `claim_run`/`release_claim`,
   `add_admin`/`remove_admin`, `TenantService.bootstrap_staff` each existed, were
   tested, and were reachable from no surface. Prose asserting a feature works is
   how an unwired capability survives review — the docs called the qualifier claim
   a lock while no browser user could set it.
3. **Drive every role the surface admits.** `scripts/seed_support.py` `USER_SPECS`
   seeds one user per role, so this is a config list, not hand-grants. A flow
   audited only as staff is a flow audited once.
4. **Use two browser contexts for a transition.** Approval, handoff, claim, release
   — anything with two sides needs both open at once. That is how the qualifier
   review race surfaced: two reviewers verdicting one run both committed and DM'd
   the runner contradictory results.
5. **Re-measure at 390×844.** Every table needs its mobile card
   (`check_table_grid` enforces the call, not that the result is usable).
6. **Count, don't characterise.** "~39 interactions for an 8-player stage" and
   "a 151,156 px page" are findings; "feels clunky" is not.

Setup and login are `/ui-validation`'s — reuse it rather than restating it, and
use `/api-validation` and `/discord-ux` for the surfaces a browser can't reach.

## What to look for, from the audits that found it

- **An id in a sentence.** "sign up as a commentator for match ID 17" — the DM
  built by the same service named the players, the time and the stage. Use
  `application/utils/match_labels.py`.
- **A call to action that names a destination instead of linking the control.**
  See the rule in CLAUDE.md; check the role gate on whatever you link to.
- **A notification that only fires one way.** Assignment DMs; un-assignment used
  to be silent. Ask what the reverse transition tells whom.
- **Config declared, populated, and read by nothing.** `LinkSectionConfig`'s
  `description` and `link_button_label` were praised by an audit that had only
  read the source. `test_every_link_section_config_field_is_rendered` is the shape
  of the fix.
- **Anything unbounded.** Nothing in the qualifier subsystem paginated.

## Writing it up

Write `docs/reviews/<topic>.md` in the shape the existing files use — scope, then
findings ranked by severity, each with the evidence that produced it. Tag any
claim you did not drive as `code-read`; an audit that praises something it only
read is worse than no audit. Add a row to the table in `docs/reviews/README.md`.

**On ship, delete the report** (`docs/README.md`: point-in-time audit reports are
not kept) and move what survives: the invariant into the feature doc, and any
recurring mechanical class into `.claude/scripts/` as a guardrail. `check_table_prefs`
and `check_slot_context`'s second check both came out of audits this way — that
is how a finding stops recurring instead of being found a tenth time.
