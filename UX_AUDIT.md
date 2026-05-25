# SGLMan — UX Audit

A review of the full UI surface (public pages, admin dashboard, dialogs, tables, reports) focused on usability, clarity, consistency, accessibility, and feedback. This is an inventory of findings, not a code change.

## Methodology

- **Scope.** Everything under `pages/`, `theme/dialog/`, `theme/tables/`, `theme/base.py`, `static/css/styles.css`, plus user-facing aspects of `middleware/auth.py`.
- **Approach.** Three parallel exploration passes (public, admin, dialogs/tables) followed by spot-verification of every suspect claim against the actual source. Findings that did not survive verification (e.g. an alleged missing audit-log expand affordance — it exists at `pages/admin_tabs/reports/audit.py:160-169`; alleged `asyncio.create_task` usage — none present anywhere in the UI) were dropped.
- **Severity.**
  - **Critical** — silent failure, data loss risk, or blocks a workflow with no feedback.
  - **Major** — common-flow friction or confusion that an attentive user will notice and complain about.
  - **Minor** — polish; does not change task completion but accumulates over time.
- **Out of scope.** Performance, backend correctness, Discord bot UX, visual design polish beyond what affects usability.

## Summary

| Severity | Findings | Themes |
|----------|----------|--------|
| Critical | 4 | Silent seed-gen failure; empty-message send; logout a11y; missing confirmation before triforce-text delete |
| Major | 23 | Spread across 11 themes below |
| Minor | 8 | Terminology, color-only state, polish |

Findings are grouped into 12 themes below. Each GitHub issue filed for this audit corresponds to one theme.

---

## Theme 1 — Required-field markers & client-side validation

**Severity: Major.** Forms have no visual indication of which fields are required and no live validation. Users learn they got it wrong only after pressing Submit.

- `theme/dialog/match_dialog.py:334-337` — Tournament / Date / Time are validated only inside `submit()` with a generic "Please fill all required fields." Required fields carry no asterisk, no border highlight, no disabled-Submit affordance.
- `theme/dialog/match_result_dialog.py:81-83` — Submit button is always enabled; clicking with no winner shows "Please select a winner" after the click instead of disabling the button.
- `theme/dialog/send_message_dialog.py:16-20` — No empty-message guard. The textarea value is passed straight to `send_callback` → `DiscordService.send_dm`. **Critical** because the bot will attempt to deliver a blank DM.
- `theme/dialog/station_assignment_dialog.py:70-77` — `placeholder='e.g., A1, B2, Station 3'` but no format validation, no length cap. Free-text gets stored verbatim.
- `theme/dialog/tournament_edit_dialog.py` — 12 fields rendered identically; required vs optional indistinguishable.
- `theme/dialog/user_edit_dialog.py` — Same: username, display name, pronouns all styled the same.
- `pages/home_tabs/player_edit_info.py` — Display name / pronouns fields lack required markers; no dirty-state warning if the user navigates away with unsaved changes.

**Reference implementation.** Adopt a single pattern: required inputs use `.props('required')`, primary action disabled via `.bind_enabled_from(...)` until the form is valid, and a small "* required" legend in the dialog header.

---

## Theme 2 — Icon-only buttons missing tooltips / labels

**Severity: Critical (logout) + Major (timeline controls).** Multiple icon-only buttons have no `.tooltip(...)` and no text label, breaking screen-reader and keyboard-only flows.

- `theme/base.py:67` — `ui.button(on_click=…, icon='logout')` in the header. No label, no tooltip. The dark-mode button immediately below (line 80) sets the example with `.tooltip('Toggle dark mode')`. **Critical** because logout is a high-stakes action that any user might need to find quickly.
- `pages/home_tabs/stage_timeline.py` — `chevron_left` / `chevron_right` / date-picker / refresh buttons (around lines 30, 37, 50, 59) have no tooltips.
- `pages/admin_tabs/triforce_texts.py:122-127` — Delete button is `icon='delete'` only; has `.tooltip('Delete')` (good) but compare to the Approve/Reject buttons that have text — inconsistent.
- `pages/admin_tabs/reports/audit.py:185-204` — Previous/Next buttons have text, but several other report pages have icon-only refresh.

**Pattern.** Every icon-only `ui.button(...)` must chain `.tooltip('action verb')`.

---

## Theme 3 — Confirmation gating for destructive actions

**Severity: Critical (triforce delete) + Major (others).** A reusable `ConfirmationDialog` exists at `theme/dialog/confirmation_dialog.py` and is correctly used for match delete (`theme/dialog/match_dialog.py:424`) and crew undo-signup. It is **not** used for triforce-text deletion.

- `pages/admin_tabs/triforce_texts.py:122-127` — Delete button calls `background_tasks.create(_delete(eid))` with no confirmation. A misclick on the trash icon deletes a moderation submission immediately. **Critical** in a moderation context where the user-submitted content is the entire deliverable.
- `pages/admin_tabs/admin_schedule.py:103-116, 157-170` — Start/Confirm use `ConfirmationDialog` (good), but the message could note the irreversibility ("Started matches cannot be un-started").
- `pages/admin_tabs/admin_schedule.py:130-143` — Finish opens `MatchResultDialog` directly without warning that this will overwrite any prior result; the dialog doesn't surface "There is an existing result of X" either.

---

## Theme 4 — Empty states & first-run guidance

**Severity: Major.** Several pages render "nothing here" as either a blank container or a one-line gray label, with no explanation of what to do next.

- `pages/home_tabs/schedule.py` — No "No matches scheduled yet" placeholder; renders an empty table.
- `pages/admin_tabs/triforce_texts.py:35-40` — "You are not an admin of any active tournament." — accurate but offers no guidance ("Ask a SUPERADMIN to grant you tournament-admin", or a link to the tournaments page).
- `pages/admin_tabs/reports/match_ops.py` — `'No matches in window.'` — gives no hint whether the window is wrong or there's no data.
- `pages/admin_tabs/reports/dashboard.py:155-156` (peak subtitle helper) — Same; "no scheduled matches in window" without a suggested next action.
- `pages/admin_tabs/admin_settings.py` — When `can_manage` is False, the "Add Stream Room" button is not rendered at all rather than disabled with a tooltip explaining permissions (see Theme 10).

**Pattern.** Empty states should answer: *what should I see here?* and *what's the next action?*

---

## Theme 5 — Loading / in-flight feedback

**Severity: Major.** Async operations frequently complete with no visible progress indicator, so users can't tell the difference between "working" and "broken."

- `pages/admin_tabs/triforce_texts.py:107-128` — Approve / Reject / Delete buttons fire and forget; no spinner on the button, no row-level "saving…" hint until the toast appears.
- `pages/admin_tabs/admin_schedule.py:59-74` — `on_generate_seed` calls a service that may run for several seconds; the table row only updates after completion. The match table does show a spinner via `update_row_by_id`, but the initial click has no instant button feedback.
- `pages/home_tabs/player.py` — `background_tasks.create(table_view.refresh())` runs with no visible loading state on the player dashboard.
- `pages/admin_tabs/reports/shared.py:158-173` (CSV export) — `ui.download(...)` fires with no success toast. A large export feels like a no-op.

**Pattern.** For any handler ≥250ms, either disable the button with a spinner (`.props('loading')`) or show a `ui.notify('Saving…')` immediately.

---

## Theme 6 — Stale data & refresh patterns

**Severity: Major.** Tables refresh only on tab activation or explicit click; concurrent edits from another admin are invisible until the page is reloaded — risky during live event ops.

- `pages/admin_tabs/admin_schedule.py:230-232` — `ui.on('selected_tab', …)` only refreshes when the Schedule tab becomes active. If two ops admins are both on Schedule, neither sees the other's edits.
- `pages/admin_tabs/admin_settings.py` — Stream-room table refresh is fire-and-forget (`background_tasks.create(refresh_table())`); if it raises, the table sits empty with no error.
- `pages/admin_tabs/admin_users.py:65-69` — Role filter triggers refresh, but no scheduled background refresh; data goes stale silently.
- `pages/admin_tabs/triforce_texts.py:140, 149` — `submissions_table.refresh()` is called synchronously after an awaited mutation; OK in isolation but there's no polling, so a second moderator's actions are invisible.
- `theme/dialog/match_dialog.py:349-354` does the right thing (concurrent-edit detection via `updated_at` comparison). That pattern should propagate to other long-lived edit surfaces.

**Pattern.** For live-ops tables, add a configurable auto-refresh ticker (the MatchTableView already has the checkbox UI — generalise it) and propagate the optimistic-concurrency pattern from `match_dialog`.

---

## Theme 7 — Timezone display consistency

**Severity: Major.** `application/utils/timezone.py` is the project standard (`format_eastern_display`, `format_eastern_datetime`, etc., per `CLAUDE.md`). Most dialogs use it correctly. A few surfaces don't.

- `theme/tables/user.py:136-137` — `u.created_at.strftime('%Y-%m-%d %H:%M')` and same for `updated_at`. These are stored UTC but rendered without conversion, so admins see UTC times in the user table without any timezone label. **Major.**
- `pages/admin_tabs/reports/dashboard.py:66` — `f'Window: {start_d.isoformat()} → {end_d.isoformat()} (US/Eastern)'`. `start_d` / `end_d` are dates here so the output is `2025-01-15`, which is benign — but bypasses `format_eastern_date`, making it fragile if the type ever becomes a `datetime`. **Minor.**

`theme/dialog/match_result_dialog.py:48-50`, `theme/dialog/station_assignment_dialog.py:51-53`, and `pages/admin_tabs/reports/audit.py:114` already use `format_eastern_datetime` / `format_eastern_display` — that's the pattern to mirror.

---

## Theme 8 — Filter state persistence & URL state

**Severity: Major.** Filters don't survive reload, and URL-encoded report state doesn't compose well across pagination + filter changes.

- `pages/admin_tabs/admin_users.py:28-33` — Selected roles live in a local `selected = {'value': []}` dict, lost on reload.
- `pages/admin_tabs/reports/audit.py:185-204` — Previous / Next buttons preserve `start`, `end`, `user_id`, `action`, `page` — but if the user changes the date range while on page 5, they stay on page 5 (likely empty). Page should reset to 1 on any non-page filter change.
- `pages/admin_tabs/reports/shared.py:178` — `navigate_with_params(...)` triggers full page reloads on every filter change; scroll position and tab focus are lost. Consider client-side filter application + history.push.
- `pages/admin_tabs/admin.py` (lines ~19-30, query params) — No "Clear filters" button anywhere; admins must manually edit the URL to escape a deep filter combination.

---

## Theme 9 — Pagination & large-data handling

**Severity: Major.** Several tables fetch unbounded result sets and rely on the browser to handle the volume.

- `pages/admin_tabs/admin_schedule.py:48-49` — `def get_query(): return Match.all()`. Across a multi-day event with hundreds of matches, every render fetches everything.
- `pages/admin_tabs/admin_users.py:42-54` — `User.all()` likewise. Filtering only affects the where-clause, not the row cap.
- `pages/admin_tabs/reports/crew.py` — Approval filter is applied **client-side** after fetching all rows; with large events this becomes laggy.
- Audit log uses proper limit/offset pagination (`pages/admin_tabs/reports/audit.py:102-106`) — that's the model to copy.

**Pattern.** Pick a sensible cap (e.g. 200) on tables, switch to repository-level pagination, and add a count badge ("Showing 200 of 547").

---

## Theme 10 — Permission UX (hide vs disable vs error)

**Severity: Major.** The codebase mixes three patterns for permission-gated UI: silent hide, runtime error, and (rarely) disabled-with-tooltip. The first two confuse users.

- `pages/admin_tabs/admin_settings.py:115-116` — When `can_manage` is False, "Add Stream Room" vanishes from the toolbar. Users wonder if it's a bug.
- `pages/admin.py:34-56` — Page renders the full BaseLayout then shows "You do not have permission" inside the content area. The chrome flash is jarring; an early redirect (or rendering only an error card) would be cleaner.
- `pages/admin.py:72-84` — Six conditional blocks decide tab visibility based on a mix of global roles and per-tournament relationships. When an admin loses a role and a tab disappears on next reload, there is no feedback explaining the change.

**Pattern.** Prefer **disabled with tooltip** ("Requires SUPERADMIN") over silent hide for any button a user might reasonably expect to see. Reserve hide for tabs where the entire section is irrelevant.

---

## Theme 11 — Mobile responsiveness

**Severity: Major.** Multiple hardcoded widths assume desktop viewports.

- `static/css/styles.css:114-117` — `.dialog-card { min-width: 700px; max-width: 90vw; }`. The `@media (max-width: 768px)` block (lines 119-124) covers phones, but **tablets in the 769-1023px range still get a 700px-wide dialog**, which overflows in portrait.
- `static/css/styles.css:350-352` — `.control-width { width: 400px; }` with no responsive fallback; on narrow phones the input overflows the column.
- `static/css/styles.css:377-381` — `.refresh-button { position: fixed; bottom: 20px; right: 20px; }` on the stage-timeline page overlaps the footer on small screens.
- Multi-field admin dialogs (notably `AdminMatchDialog`) have no scroll/overflow handling; tall forms exceed viewport height on laptops.

**Pattern.** Replace `min-width` with `max-width` for dialogs and add `overflow-y: auto; max-height: 90vh` to dialog cards.

---

## Theme 12 — Jargon & inconsistent terminology

**Severity: Minor — but pervasive enough to merit a sweep.**

- `pages/admin_tabs/admin_schedule.py:35-36` and `pages/home_tabs/player.py` — Column labeled `Acks` (abbreviation of "Acknowledgments"). Users may read it as "Acks" the word.
- `pages/admin_tabs/reports/crew.py:131` — Column labeled `Comms (apprv/total)` — "Comms" could be communications or commentators; "apprv" is a non-standard abbreviation.
- `pages/admin_tabs/reports/crew.py:121` — Cell renders `GAP` with no header explanation of what counts as a gap (no commentator? no tracker? both?).
- `theme/tables/tournament.py:34` — Column `staff_administered` is the raw field name, surfaced as the user-facing header.
- Tab labels mix metaphors: "On Air" vs other places using "Timeline" / "Stage Timeline" for the same concept.
- Button label drift: "Save" (match_dialog), "Update"/"Create" (tournament_edit_dialog), "Submit" (new-match flow), "Submit Results" (match_result_dialog), "Assign Stations". Action-verb labels are good, but the same operation (commit changes) should use the same word.

**Pattern.** A short glossary + a single-sweep PR to spell out abbreviations and unify Save/Update/Submit.

---

## What this audit does **not** cover

- Performance / query plans / N+1 risk in the ORM layer.
- Backend correctness (the service-layer tests in `tests/services/` exercise that well).
- Discord bot UX (Slack/Discord notification copy, embeds, buttons).
- Visual design polish (typography, palette, spacing) beyond what blocks task completion.
- Internationalisation / right-to-left.
