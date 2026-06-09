# Feature: Triforce Texts

_Added: PR #14 | Status: Stable_

## What It Does

A player submission system for ALTTP (A Link to the Past) end-game triforce screen lines, ported from sahasrahbot. Players submit custom text lines that appear on the triforce screen. Admins moderate (approve/reject) each submission.

## Page Route

`/triforcetexts/{tournament_id}` — requires login. Only players enrolled in that tournament can submit.

## Submission Flow

1. Player navigates to `/triforcetexts/{tournament_id}`.
2. Fills out the triforce text form (multiple lines, character limits enforced).
3. Submits — `TriforceTextService.submit()` stores the entry with `approved=False`.
4. Admin reviews pending submissions in the admin dashboard under "Triforce Texts" tab.
5. Admin approves or rejects. Approved texts are exported/used for the game ROM.

## Moderation

- Admin view: `pages/admin_tabs/triforce_texts.py`
- Delete is confirmation-gated via `ConfirmationDialog` (PR #31 fix).
- Approve/Reject buttons call `TriforceTextService.approve()` / `TriforceTextService.reject()`.
- All approve/reject/delete actions are written to `AuditLog`.

## Key Files

| File | Role |
|---|---|
| `models.py` → `TriforceText` | Model with player FK, tournament FK, text lines, `approved` bool, `rejected` bool |
| `pages/triforce_texts.py` | Player submission page |
| `pages/admin_tabs/triforce_texts.py` | Admin moderation tab |
| `application/services/triforce_text_service.py` | Business logic: submit, approve, reject, delete |
| `application/repositories/` (triforce) | ORM queries for TriforceText |

## Character/Format Constraints

Character limits and line count restrictions are enforced in `TriforceTextService.submit()`. Any violation raises `ValueError` which the UI catches and displays via `ui.notify()`.

## Per-Tournament Scope

Each `TriforceText` row is linked to a specific `Tournament`. Players see only the submission form for tournaments they are enrolled in. Admins see all submissions filterable by tournament.
