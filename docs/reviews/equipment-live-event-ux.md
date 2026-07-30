# Equipment UX at a live event — evaluation

**Scope:** the on-site lending loop — the asset page a QR scan lands on
([`pages/equipment.py`](../../pages/equipment.py)), the checkout/check-in dialogs
([`checkout_dialog.py`](../../theme/dialog/checkout_dialog.py)), the printable
label sheet ([`equipment_labels.py`](../../pages/equipment_labels.py)), the admin
register ([`admin_equipment.py`](../../pages/admin_tabs/admin_equipment.py)) and
the borrower's own tab ([`home_tabs/equipment.py`](../../pages/home_tabs/equipment.py)),
over [`EquipmentService`](../../application/services/equipment_service.py).
Behind `FeatureFlag.EQUIPMENT`.

**Method:** drove the running app against the seeded `default` tenant **at
390×844 throughout** (this flow is used standing up), simulating a scan by
navigating straight to `/t/default/equipment/<id>` as: nobody (signed out),
`staff_user`, and `player_three` / `player_two` (plain volunteers). Checked an
asset out and watched a second session see it, clicked check-in during a forced
offline interval, and rendered the label sheet. Every number below is measured.

**Headline:** the scan → login → asset path works, which is the thing most likely
to have been broken: the deep link survives the Discord round trip and lands on
the right asset. Two things do not. The **volunteer who can take a cable out
cannot put it back** — check-out admits volunteers, check-in is
manager-only — and an action clicked during a network blip is **silently lost**:
no error, no retry, the page still says "Checked out". Also, the post-login
redirect lands on a URL with the tenant prefix applied twice.

---

## The measured shape

| Journey | Result |
|---|---|
| Signed-out scan of `/t/default/equipment/1` | HTTP 200 → `/t/default/login` (mock picker) |
| …then log in | lands on the asset — **but at `/t/default/t/default/equipment/1`** (F3) |
| Staff scan → checked out | **4 interactions** (Check out… → Borrower select → pick → Check out) → `Checked out.` |
| Asset page height at 390×844 | 844–886 px — fits a phone, no horizontal overflow |
| Checkout dialog | 1 select, `Borrower / Cancel / Check out` |
| Borrower options offered | **11 — every `User` on the platform, `System` included** |
| Second session viewing the same asset | `Checked out` badge + `Checked out to System (2026-07-30 07:09 EDT)` + Check in. Check-out button correctly gone |
| Label sheet `?ids=1,2,3` | 3 labels, 3 QR images, a `PRINT` button, 1,400 px |

By role, scanning the same label:

| Who | Available asset | Checked-out asset |
|---|---|---|
| `staff_user` (manage) | `Check out…` (choose borrower), Edit, Print label, Download QR | `Check in`, Edit, … |
| volunteer (`player_two`, `player_three`) | `Check out to me` | **no actions at all** |
| signed out | login redirect | login redirect |

Network interruption, measured on a real checked-out asset:

| Step | What the operator sees |
|---|---|
| Go offline, click **Check in** | nothing — no notification, no error, no disabled state, no connection overlay |
| Wait 4 s | unchanged |
| Reconnect, wait 5 s | still `Checked out`, still no notification. **The click is gone** |

---

## Root causes

### RC1 — Taking out and putting back are gated differently, and the page says nothing about the gap

[`auth_service.py:262-271`](../../application/services/auth_service.py#L262):
`can_checkout_equipment` admits staff, equipment managers **and volunteers**
(*"volunteers may only check out to themselves"*); `can_checkin_equipment` is
`can_manage_equipment` — staff and equipment managers only. The asset page renders
buttons purely from those predicates
([`equipment.py:114-121`](../../pages/equipment.py#L114)), so a volunteer holding a
cable scans its label, sees the asset, sees who has it (themselves), and sees
**nothing to click**.

### RC2 — The page assumes the socket is up

Every action is a NiceGUI event over the WebSocket. There is no optimistic UI, no
queued retry, and no visible connection state on this page — so on a venue network
the difference between "done" and "the click never left the phone" is invisible.
The seeded run above lost a check-in with no trace.

### RC3 — The borrower list is the global user table

The checkout dialog's Borrower select offers all 11 platform users including the
`System` service account (measured — the audit's own checkout went to `System`).
Same root as
[new-tenant-onboarding-ux F2](new-tenant-onboarding-ux.md#f2--critical--a-brand-new-communitys-users-tab-lists-every-user-on-the-platform):
`User` is global, nothing narrows it to this community, and no surface filters out
service accounts.

---

## Findings, ranked

### F1 — Critical · A volunteer can take equipment out but cannot check it back in

Measured both directions (RC1). At a live event this means every return has to
find a staff member, and the person holding the item gets no hint of that: the
scanned page simply has no buttons. Either check-in should admit the current
borrower for their own loan (the mirror of "volunteers may only check out to
themselves"), or the page must say *"ask an equipment manager to check this in"* —
right now it says nothing at all.

### F2 — Critical · An action taken during a network blip is silently lost

Measured (RC2): offline click → no feedback → reconnect → state unchanged, no
notification. On a venue Wi-Fi this is the difference between an asset the system
thinks is out and an asset sitting back in the box. The minimum fix is visible
connection state on this page plus a failed-action notice; NiceGUI's
disconnect handling is the lever, and this is the one surface where it matters
most.

### F3 — Major · The post-login redirect doubles the tenant prefix

Reproduced twice: scan `/t/default/equipment/3` while signed out → log in → land
on **`/t/default/t/default/equipment/3`**. The page renders (HTTP 200, correct
asset, survives a reload), so today it is cosmetic — but it means the stored
return path already carries the tenant prefix and something prefixes it again.
Any stricter routing, a custom-domain tenant, or a link a volunteer copies out of
the address bar and shares is where this stops being cosmetic.

### F4 — Major · The mobile register's row actions are four unlabelled icons, one of which deletes

The card grid at 390×844 renders `#`, Name, Owner, Status, Checked out to, then
four icon-only buttons: check-out, QR, edit, **delete**. No labels, tooltip-only
explanations — and the proctor-board work already established in this codebase
that *"the proctor reads this board on a tablet, where a tooltip never opens"*
([`match_slots.py:349-352`](../../theme/tables/match_slots.py#L349)). Delete sits
one thumb-width from Edit.

### F5 — Minor · The borrower picker offers the whole platform, including `System`

RC3, measured: 11 options, and the checkout succeeded against `System`, which then
appeared on the asset page as *"Checked out to System"*. Nothing filters to this
community's people, to volunteers, or away from service accounts.

### F6 — Minor · Loan history is an unbounded list of plain text lines

[`equipment.py:124-137`](../../pages/equipment.py#L124) renders one caption line
per loan (`borrower: out → back (out by X)`) with no limit, no grouping and no
collapse. A cable lent 200 times pushes the action buttons — which are rendered
*above* it, so the ordering is right — but makes the page an endless scroll on the
device where scrolling costs the most.

### F7 — Minor · The printed QR encodes whatever `BASE_URL` says, discoverable only by scanning a printed label

The page shows the encoded link as a caption under the QR (good — measured
`http://localhost:8000/t/default/equipment/3` in dev), so a misconfiguration is
*visible* if someone reads it, but nothing validates that the host matches the one
the operator is browsing. A batch of labels printed against a stale `BASE_URL` is
only discovered when someone scans one at the venue.

---

## What works

- **The scan path itself.** Signed-out deep link → login → the correct asset. The
  tenant-qualified link is built deliberately
  ([`equipment.py:60-69`](../../pages/equipment.py#L60)) with a comment explaining
  why a bare `/equipment/<id>` would 404, and it holds up.
- **Conflict display.** A second viewer sees the `Checked out` badge, the borrower
  and the timestamp, and the check-out button is gone rather than present-and-failing.
- **Private notes and owner labels are properly gated** — a volunteer's scan showed
  neither (`can_manage` only), and `get_user_from_discord_id` enforces `is_active`
  so a deactivated account cannot keep reading them.
- **The asset page fits a phone** (844–886 px, no horizontal overflow) with the QR,
  the status, the holder and the actions all above the history.
- **The borrower's own tab** has `INVENTORY` and `MY CHECKOUTS` sub-tabs and shows
  the whole inventory with statuses and holders — the "what do I have" view F1's
  scanned page lacks.
- **The label sheet** renders one label per asset with a Print button and no
  surprises.

## Not covered

A real device pass (everything here is emulated Playwright at 390×844 — per
[current-state.md](../current-state.md) no physical-device run has ever happened,
and F2 in particular deserves one), real camera scanning of a printed label, and
the equipment REST endpoints.
