# Wave 2 — The phone tells the truth about what you can do (F3, F7, F5)

**Read [README.md](README.md) first.** In particular: the check-in gate is
**settled** — this wave explains it, never widens it — and the equipment tables
keep their bespoke `item` slots rather than adopting `enable_mobile_grid`.

**Goal:** at 390×844, every control says what it does, the one that deletes is not
a thumb-width from the one that edits, a volunteer holding a cable learns what to
do next, and an asset with a long history is still a usable page.

Presentation, plus one bounded read (task 2.3) and one seed extension (task 2.4).

---

## Task 2.1 — Label the register's card actions and separate the destructive one

**Where:** [`admin_equipment.py`](../../../pages/admin_tabs/admin_equipment.py) —
the `item` slot (currently lines 93-131). Leave the desktop
`body-cell-actions` slot as icons: a tooltip does open on a mouse, and the wide
row has no room for four labels.

At 390 px the card currently ends in four icon-only `q-btn`s — check-out/check-in,
QR, edit, **delete** — explained only by `q-tooltip`. The precedent is already in
this codebase: *"the proctor reads this board on a tablet, where a tooltip never
opens"*
([`match_slots.py:349-352`](../../../theme/tables/match_slots.py#L349)), which is
why the proctor card's buttons carry text.

Do the same here:

- Labelled buttons in the card: **Check out** / **Check in**, **Open**, **Edit**,
  **Delete** (icon + text, `no-caps`, matching the proctor card's treatment).
- **Delete leaves the row.** Put it visually apart from Edit — its own line, or
  right-aligned after a spacer — and keep it `outline` negative rather than a flat
  icon. A destructive control that looks identical to its neighbour is the finding;
  colour alone did not fix it.
- Keep the `ConfirmationDialog` that already guards it (`handle_remove`) — the gap
  was labelling and adjacency, not confirmation.
- The card and the desktop slot must stay consistent about *which* actions exist
  for a row (the `v-if` on `status_value` is load-bearing: no check-out on a
  checked-out asset).

Do the same labelling pass on
[`home_tabs/equipment.py`](../../../pages/home_tabs/equipment.py)'s
`checkout_btn` / `checkin_btn` / `view_btn` card snippets — the volunteer's own
inventory tab has the same icon-only cards, minus the delete.

**Tests:** `tests/theme/` string assertions that each equipment card slot contains
the visible words (`Check out`, `Check in`, `Edit`, `Delete`) and not a bare
icon-only delete. Model it on `tests/theme/test_match_slot_templates.py`.

**Docs:** the admin-equipment and home-equipment sections of
[`docs/reference/frontend.md`](../../reference/frontend.md).

---

## Task 2.2 — Tell the volunteer what to do instead

**Where:** [`pages/equipment.py`](../../../pages/equipment.py), under the actions
row (currently lines 114-121).

Measured: a volunteer scanning the label of the asset **they are holding** gets a
name, a status badge, a holder line, and **no controls at all** — nothing
distinguishing "you are not the one who records returns" from "this page is
broken".

Render a single line when the viewer sees no action for a checked-out asset — i.e.
`open_loan is not None and not can_checkin` — using the audit's copy:

> Returns are recorded by staff or an equipment manager — hand it to them to check
> in.

Two variants, because the page already knows which applies:

- viewer **is** the current borrower → lead with *"You have this checked out."*
  then the sentence above;
- viewer is not → the holder line already names who has it; the sentence stands
  alone.

Constraints:

- Never render it for a manager (they have the button).
- It is presentation-derived from the predicates the page already computed
  (`can_checkin`, `open_loan.borrower_id`, `user.id`) — no new service call.
- A retired asset that offers nothing to a volunteer deserves the same courtesy:
  one line saying it is retired and cannot be checked out. Cheap while you are
  here, and it closes the other actionless state.

**Tests:** a `tests/theme/`-style assertion on the copy is weak here since the
branch is inside a page function; prefer the measurement pass (task 2.5) as the
proof and say so. If the branch can be factored into a small pure helper
(`equipment_guidance(...) -> str | None`) put it in `theme/` and unit-test it —
that is the shape worth having.

**Docs:** the asset-page section of
[`docs/reference/frontend.md`](../../reference/frontend.md), and the same sentence
should be the one place the *reason* for the asymmetric gate is written down for
users.

---

## Task 2.3 — Bound the loan history at the read, not just the render

**Where:** [`pages/equipment.py`](../../../pages/equipment.py) (lines 124-137),
[`EquipmentService.loan_history`](../../../application/services/equipment_service.py),
[`EquipmentRepository.list_loans_for_equipment`](../../../application/repositories/equipment_repository.py).

Today the page renders one caption line per loan with no limit, no grouping and no
collapse, and the service loads **every** loan with its borrower prefetched. A
cable lent 200 times is 200 rows fetched and 200 lines painted on the device where
scrolling costs most.

- Repository: accept a `limit` and return a count (or expose a small
  `count_loans_for_equipment`) so the page can say *"5 of 213"*.
- Service: pass it through — `loan_history(asset, limit=...)`; keep the existing
  callers working.
- Page: render the most recent 5, then a **Show all** expansion
  (`ui.expansion`) that fetches the rest on demand. Keep the actions row above the
  history — the audit confirmed that ordering is already right.
- While here: a still-open loan currently reads `borrower: out → still out`. Give
  it a badge or a bolder marker so the current holder is scannable rather than
  parsed.

Watch the layer boundary: the *limit* is data access, the *"5 of 213"* string and
the expansion are presentation. Do not let a formatted string be returned from the
service.

**Tests:** `tests/services/test_equipment_service.py` — the limit is honoured, the
count is the total, ordering is most-recent-first, and an asset with zero loans
still returns cleanly. These fail without the change.

**Docs:** [`docs/reference/services.md`](../../reference/services.md) (the changed
signature) and the asset-page section of
[`docs/reference/frontend.md`](../../reference/frontend.md).

---

## Task 2.4 — Seed the fixtures these findings need

**Where:** the equipment block of
[`scripts/seed_dev.py`](../../../scripts/seed_dev.py) (currently lines 514-553).

The audit had to grant roles by hand — a theme the reviews README already calls out
("the dev seed cannot produce the roles that expose the worst bugs"). Add, per
tenant, idempotently and tenant-scoped like the rows around them:

- **An equipment-manager-only user** (`EQUIPMENT_MANAGER`, *not* `STAFF`) — today
  `staff_user` holds both, so nothing proves the manager path works without staff.
- **A volunteer currently holding an asset** — an open `EquipmentLoan` whose
  borrower is a plain `VOLUNTEER`. Without it, task 2.2's dead end cannot be
  reproduced by logging in as that volunteer and scanning their own item.
- **An asset with a long history** — ~15 closed loans on one asset, so task 2.3's
  bound is visible and the "5 of N" line has a real N.

Keep the existing four assets and their two loans as they are; other audits and
screenshots depend on them.

**Tests:** `tests/test_seed_coverage.py` if it asserts on shapes the new rows
affect; otherwise the proof is a clean `seed_dev.py` run twice (idempotence) with
the new logins working.

---

## Task 2.5 — Re-measure at 390×844, as three roles

Drive the seeded `default` tenant and record, in the audit's format:

| Journey | What to record |
|---|---|
| Manager on `/admin/equipment` at 390 px | every card action's visible label; the pixel gap between Edit and Delete |
| Volunteer scanning the asset **they hold** | the guidance line, verbatim |
| Volunteer scanning an asset someone else holds | the holder line + guidance line |
| Manager scanning the long-history asset | page height, history lines shown, the "N of M" text |
| Equipment-manager-only user, every surface above | that nothing is missing versus `staff_user` |

Screenshot each at 390×844 and 1500 px. No horizontal overflow, no new console
errors, and the asset page height for the long-history asset should be in the same
range the audit measured for a short one (844–886 px).
