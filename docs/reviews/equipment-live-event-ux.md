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
the right asset. The real problem is what happens when the network hiccups — an
action clicked during a blip is **silently lost**: no error, no retry, the page
still says "Checked out". Second: the post-login redirect lands on a URL with the
tenant prefix applied twice. The asymmetric gate (volunteers may check out, only
staff and equipment managers may check in) is **deliberate**; the only thing worth
changing there is that the page never says so (F7).

---

## The measured shape

| Journey | Result |
|---|---|
| Signed-out scan of `/t/default/equipment/1` | HTTP 200 → `/t/default/login` (mock picker) |
| …then log in | lands on the asset — **but at `/t/default/t/default/equipment/1`** (F2) |
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

### RC1 — Taking out and putting back are gated differently *by design*, and the page never says so

[`auth_service.py:262-271`](../../application/services/auth_service.py#L262):
`can_checkout_equipment` admits staff, equipment managers **and volunteers**
(*"volunteers may only check out to themselves"*); `can_checkin_equipment` is
`can_manage_equipment` — staff and equipment managers only.

**This asymmetry is intentional** — check-in is reserved for staff and equipment
managers so that a return is recorded by someone accountable for the item actually
coming back, not by the person handing it over. Treat it as settled; it is not a
finding.

What follows from it *is* a presentation gap. The asset page renders buttons purely
from those predicates ([`equipment.py:114-121`](../../pages/equipment.py#L114)), so a
volunteer holding a cable scans its label, sees the asset, sees who has it
(themselves), and sees **nothing to click** — with no indication that returning it
means finding a manager rather than that the page is broken (F7).

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

### F1 — Critical · An action taken during a network blip is silently lost

Measured (RC2): offline click → no feedback → reconnect → state unchanged, no
notification. On a venue Wi-Fi this is the difference between an asset the system
thinks is out and an asset sitting back in the box. The minimum fix is visible
connection state on this page plus a failed-action notice; NiceGUI's
disconnect handling is the lever, and this is the one surface where it matters
most.

### F2 — Major · The post-login redirect doubles the tenant prefix

Reproduced twice: scan `/t/default/equipment/3` while signed out → log in → land
on **`/t/default/t/default/equipment/3`**. The page renders (HTTP 200, correct
asset, survives a reload), so today it is cosmetic — but it means the stored
return path already carries the tenant prefix and something prefixes it again.
Any stricter routing, a custom-domain tenant, or a link a volunteer copies out of
the address bar and shares is where this stops being cosmetic.

### F3 — Major · The mobile register's row actions are four unlabelled icons, one of which deletes

The card grid at 390×844 renders `#`, Name, Owner, Status, Checked out to, then
four icon-only buttons: check-out, QR, edit, **delete**. No labels, tooltip-only
explanations — and the proctor-board work already established in this codebase
that *"the proctor reads this board on a tablet, where a tooltip never opens"*
([`match_slots.py:349-352`](../../theme/tables/match_slots.py#L349)). Delete sits
one thumb-width from Edit.

### F4 — Minor · The borrower picker offers the whole platform, including `System`

RC3, measured: 11 options, and the checkout succeeded against `System`, which then
appeared on the asset page as *"Checked out to System"*. Nothing filters to this
community's people, to volunteers, or away from service accounts.

### F5 — Minor · Loan history is an unbounded list of plain text lines

[`equipment.py:124-137`](../../pages/equipment.py#L124) renders one caption line
per loan (`borrower: out → back (out by X)`) with no limit, no grouping and no
collapse. A cable lent 200 times pushes the action buttons — which are rendered
*above* it, so the ordering is right — but makes the page an endless scroll on the
device where scrolling costs the most.

### F6 — Minor · The printed QR encodes whatever `BASE_URL` says, discoverable only by scanning a printed label

The page shows the encoded link as a caption under the QR (good — measured
`http://localhost:8000/t/default/equipment/3` in dev), so a misconfiguration is
*visible* if someone reads it, but nothing validates that the host matches the one
the operator is browsing. A batch of labels printed against a stale `BASE_URL` is
only discovered when someone scans one at the venue.

### F7 — Minor · A volunteer scanning the item they hold sees an actionless page and no reason why

The gate itself is settled (RC1): check-in is staff / equipment-manager only, by
design. But measured, a volunteer scanning a label for the asset **they are
currently holding** gets the asset name, the status badge, the holder line — and no
controls at all. Nothing distinguishes "you are not the one who records returns"
from "this page is broken", and nothing tells them what to do instead.

One line under the actions row covers it — *"Returns are recorded by staff or an
equipment manager — hand it to them to check in."* — and turns a dead end into an
instruction. Worth pairing with the current holder's name (already on the page)
when the viewer is not the holder.

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
- **The check-out / check-in split is enforced in the service, not just the page** —
  `can_checkout_equipment` and `can_checkin_equipment` are separate predicates, so
  the rule holds for the REST API and any future surface, not only this button row.
- **The borrower's own tab** has `INVENTORY` and `MY CHECKOUTS` sub-tabs and shows
  the whole inventory with statuses and holders — the "what do I have" view the
  scanned page lacks (F7).
- **The label sheet** renders one label per asset with a Print button and no
  surprises.

## Not covered

A real device pass (everything here is emulated Playwright at 390×844 — per
[current-state.md](../current-state.md) no physical-device run has ever happened,
and F1 in particular deserves one), real camera scanning of a printed label, and
the equipment REST endpoints.
