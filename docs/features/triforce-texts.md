# Feature: Triforce Texts

_Added: PR #14 | Status: Stable_

## What It Does

A player submission system for ALTTP (A Link to the Past) end-game triforce screen lines, ported from sahasrahbot. Players submit custom text lines that appear on the triforce screen. Admins moderate (approve/reject) each submission.

## Location

Both submission and moderation are home/admin **tabs**, not standalone page routes:

- Submission: the "Triforce Texts" home tab (`pages/home_tabs/triforce_texts.py`, `triforce_texts_tab()`) — requires login and inline tournament selection.
- Moderation: the "Triforce Texts" admin tab (`pages/admin_tabs/triforce_texts.py`).

## Submission Flow

1. Player opens the "Triforce Texts" home tab and picks a tournament that is accepting submissions.
2. Fills out the triforce text form (multiple lines, character limits enforced).
3. Submits — `TriforceTextService.submit()` stores the entry with `approved=None` (pending).
4. Admin reviews pending submissions in the admin dashboard under the "Triforce Texts" tab.
5. Admin approves or rejects. Approved texts are exported/used for the game ROM.

## Moderation

- Admin view: `pages/admin_tabs/triforce_texts.py`
- Delete is confirmation-gated via `ConfirmationDialog` (PR #31 fix).
- A single `TriforceTextService.moderate(text_id, approved, actor)` method handles both approve and reject — pass `approved=True` to approve, `approved=False` to reject.
- All moderate/delete actions are written to `AuditLog`.

## Key Files

| File | Role |
|---|---|
| `models.py` → `TriforceText` | Model with user FK, tournament FK, `text`, `author`, tristate `approved` (nullable bool: `None`=pending, `True`=approved, `False`=rejected), `approved_by`/`approved_at` |
| `pages/home_tabs/triforce_texts.py` | Player submission tab |
| `pages/admin_tabs/triforce_texts.py` | Admin moderation tab |
| `application/services/triforce_text_service.py` | Business logic: submit, moderate, delete |
| `application/repositories/` (triforce) | ORM queries for TriforceText |

## Character/Format Constraints

Character limits and line count restrictions are enforced in `TriforceTextService.submit()`. Any violation raises `ValueError` which the UI catches and displays via `ui.notify()`.

## Per-Tournament Scope

Each `TriforceText` row is linked to a specific `Tournament`. The submission tab lists tournaments that are accepting submissions; submitting is gated on `AuthService.can_submit_triforce_text` (a paid option per tournament). Admins see all submissions filterable by tournament.

**See also:** [reference/seed-generation.md](../reference/seed-generation.md) — how approved texts integrate with ALTTPR seed generation; [reference/frontend.md](../reference/frontend.md) — submission page and moderation tab internals.
