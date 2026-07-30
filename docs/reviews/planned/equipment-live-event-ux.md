# Brief — Equipment UX at a live event

Scope, method and leads for an audit nobody has run yet. Leads below are
unverified suspicions from reading the code; the audit confirms or refutes each
one against the running app.

## Scope

The on-site lending loop, phone in hand:

- [`pages/equipment.py`](../../../pages/equipment.py) — the asset detail page a
  QR scan lands on (`/equipment/{asset_id}`), with its checkout / check-in
  buttons, loan history and QR block.
- [`pages/equipment_labels.py`](../../../pages/equipment_labels.py) — the
  printable label sheet.
- [`theme/dialog/checkout_dialog.py`](../../../theme/dialog/checkout_dialog.py),
  [`equipment_dialog.py`](../../../theme/dialog/equipment_dialog.py),
  [`qr_label_dialog.py`](../../../theme/dialog/qr_label_dialog.py).
- [`admin_tabs/admin_equipment.py`](../../../pages/admin_tabs/admin_equipment.py)
  (the asset register) and
  [`home_tabs/equipment.py`](../../../pages/home_tabs/equipment.py) (what a
  borrower sees).
- [`application/services/equipment_service.py`](../../../application/services/equipment_service.py).

Feature-gated behind `FeatureFlag.EQUIPMENT`; role-gated on EQUIPMENT_MANAGER /
STAFF.

## Why this one

Every other surface in this app is used sitting down. This one is used standing in
a venue, on a phone, on venue wifi, with someone waiting for the cable. Two facts
make it the highest-value mobile audit:

- **All mobile verification in this project is emulated.**
  [current-state.md](../../current-state.md) says so explicitly, and singles out
  the untested cases: the NiceGUI WebSocket lifecycle across screen lock and
  resume, and the native date/time pickers. A QR scan resumes a backgrounded
  browser — precisely the untested path.
- **It is the one flow with real production usage on record.** Telemetry for
  `sgl26` shows a single `/equipment/{asset_id}` view: someone scanned a label.

## What to measure

1. **Scan to checkout.** Simulate the scan by navigating directly to
   `/t/<slug>/equipment/<id>` in a fresh mobile context, then count interactions to
   check the asset out to a person, and again to check it back in. Capture every
   notification verbatim.
2. **Scan while signed out.** The page renders "You must be logged in to view this
   page." ([`equipment.py:42`](../../../pages/equipment.py#L42)) — measure what
   actually happens end to end: does the deep link survive the Discord login round
   trip and land back on the asset, or does the volunteer arrive at a home page
   having lost the asset they scanned? This is the single most likely real-world
   failure in the flow.
3. **Scan while signed in as the wrong role.** A volunteer without
   EQUIPMENT_MANAGER scans a label: what do they see, and is it useful (asset
   identity, current holder) or a bare refusal?
4. **Conflict states.** Check out an asset that is already out; check in one that is
   already in; two people checking out the same asset near-simultaneously. Does the
   service refuse cleanly and does the page say who has it?
5. **Degraded network.** Drive the checkout with Playwright network throttling and
   with an offline interval mid-action. NiceGUI is WebSocket-driven; establish what
   the page does when the socket drops mid-checkout — does it retry, does it lie,
   does it silently do nothing?
6. **The label sheet.** Render `/equipment/qr-labels?ids=…` for one asset and for
   many; check page breaks, label size, and whether the encoded URL is the
   tenant-qualified one (the code says it is —
   [`equipment.py:60`](../../../pages/equipment.py#L60) — verify against a real
   scan of the rendered PNG).
7. **The register at scale.** Measure `admin_equipment` and the borrower's tab at a
   realistic asset count; extend `seed_dev.py` if the fixtures are too thin and say
   so.
8. **390×844 throughout**, plus one pass at 360×800.

## Leads to verify

- The asset page shows "Private notes" conditionally
  ([`:94`](../../../pages/equipment.py#L94)) — confirm who can see them, and that a
  scan by a borrower cannot.
- Loan history is rendered inline; check whether it grows unbounded on a
  long-serving asset and pushes the action buttons off a phone screen.
- `Download QR` uses `ui.download` on a phone — verify it produces something
  usable rather than a silent no-op.
- Check whether anything tells a borrower what they currently hold, and whether
  overdue loans are visible to anyone (compare My Shifts, which does this for
  volunteer commitments).

## Fixtures and roles

`seed_dev.py` seeds equipment and loans on `default`. Drive as `staff_user`, as an
**EQUIPMENT_MANAGER-only** account (grant by hand; the seed does not create one —
record it as a seed gap), and as a plain player. Run
`scripts/ui_flag_sweep.sh` if any shared surface is touched, since equipment is
flag-gated.

## Deliverable

`docs/reviews/equipment-live-event-ux.md`. Where a finding depends on real hardware
rather than emulation, say so explicitly and mark it as needing a device pass — do
not present an emulated result as a device result.
