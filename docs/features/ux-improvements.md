# Feature: UX Improvements (PRs #29–#33)

_Added: PRs #29 (audit), #30 (timezone), #31 (confirm delete), #32 (tooltips), #33 (validation) | Status: Stable_

## PR #29 — UX Audit

A comprehensive audit of the full UI surface. Findings organized into 12 themes across Critical / Major / Minor severity. The audit document lives at `docs/ux-audit.md`. PRs #30–#33 address the Critical and Major findings.

## PR #30 — Timezone Display Consistency (issue #23)

**Problem:** User table and some report timestamps were displaying raw UTC instead of US/Eastern.

**Fix:** Applied `format_eastern_display()` consistently across:
- `pages/admin_tabs/admin_users.py` — user last-login column
- `pages/admin_tabs/reports/` — match export date columns
- Any `DatetimeField` rendered directly in a table that was previously using `.isoformat()` or str conversion

## PR #31 — Confirmation Before Triforce Text Delete

**Problem:** Admin triforce-text delete button called delete immediately with no confirmation.

**Fix:** Wrapped delete in `ConfirmationDialog` (which already existed in `theme/dialog/confirmation_dialog.py` and was correctly used for match delete). Now:

```python
# pages/admin_tabs/triforce_texts.py
async def _delete(entry_id: int):
    async def confirmed():
        await TriforceTextService.delete(entry_id, actor=current_user)
        await refresh_table()
    ConfirmationDialog("Delete this triforce text?", on_confirm=confirmed).open()
```

## PR #32 — Tooltips on Icon-Only Buttons

**Problem:** Multiple icon-only buttons had no accessible label or tooltip (including the Logout button — high-stakes action).

**Fix:** Added `.tooltip('label')` to every `ui.button(icon=...) ` that lacked one:
- `theme/base.py` — Logout button
- `pages/home_tabs/stage_timeline.py` — date navigation buttons (prev/next day, date picker, refresh)
- Other icon-only buttons identified in the audit

**Pattern for all future icon-only buttons:**
```python
ui.button(icon='logout', on_click=logout).tooltip('Log out')
```

## PR #33 — Required Field Markers + Form Validation

**Problem:** Forms gave no visual cue about required fields; validation errors only appeared after submit.

**Fix applied across:**
- `theme/dialog/match_dialog.py` — Tournament, Date, Time marked required; Submit disabled until all required fields have values
- `theme/dialog/match_result_dialog.py` — Submit disabled until winner selected
- `theme/dialog/tournament_edit_dialog.py` — Required fields marked
- `theme/dialog/user_edit_dialog.py` — Required fields marked
- `pages/home_tabs/player_edit_info.py` — Required fields marked

**Pattern:**
```python
# Mark a field required (shows asterisk in Quasar)
ui.input('Tournament').props('required')

# Disable submit until valid
submit_btn = ui.button('Submit', on_click=submit)
submit_btn.bind_enabled_from(form_state, 'is_valid')
```

## Still Open (from UX audit)

- Empty-message guard on `send_message_dialog.py` — blank DM can still be sent.
- Station assignment format validation (free-text, no length cap).
- Themes 6–12 (minor polish items from the audit).

**See also:** [reference/frontend.md](../reference/frontend.md) — pages, dialogs, and table component internals.
