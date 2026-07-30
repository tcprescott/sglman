# Wave 3 — The borrower picker offers this community's people (F4)

**Read [README.md](README.md) first.** This is the only wave that reaches the
repository layer, and the only one that **stops for a decision before any code is
written.**

**Goal:** a manager checking an asset out picks from the people of this community,
not from every `User` on the platform, and never from a service account.

---

## The open decision — get sign-off first

Measured: the Borrower select is `UserService.get_all_users()` — 11 options in the
seeded tenant, every platform `User`, `System` included, and the audit's own
checkout landed on `System`, which then appeared on the asset page as *"Checked out
to System"*.

Three things are uncontroversial and go in regardless:

1. **Exclude the system account** (`discord_id == SYSTEM_USER_DISCORD_ID`). Nothing
   should ever lend a cable to the automation actor.
2. **Exclude deactivated accounts.** `UserRepository.get_all` does not filter
   `is_active`, so the picker currently offers people who cannot even log in —
   while `get_user_from_discord_id` refuses them everywhere else.
3. **Keep the current holder resolvable.** Whoever holds an asset must remain
   displayable and check-in-able even if they later fall out of whatever set we
   choose.

What needs a decision is **what "this community's people" means**, and there is a
hard constraint the audit did not surface:

> **`TenantMembership` is not maintained by the running app.** Rows come from the
> multitenancy migration backfill, `scripts/seed_dev.py`, `scripts/seed_tenant.py`
> and `scripts/grant_staff.py`. `TenantService.add_member` exists and **has no
> caller**; `TenantService.is_member` has none either. A user provisioned by a
> Discord login today gets **no** membership row. Scoping the picker to
> `TenantMembership` would therefore hide real people — including, at a venue, the
> volunteer standing in front of you.

So:

- **Option A (recommended) — derive from what the app actually maintains.** The
  community's people = users holding any `UserRole` in this tenant ∪ users enrolled
  in this tenant's tournaments (`TournamentPlayers` → `Tournament.tenant`) ∪ the
  asset's current holder. Both inputs are written by live code paths, so the set is
  never stale-empty. Add a **"Search all platform users"** opt-in inside the dialog
  for the genuine on-site case of a borrower who is new to the community.
- **Option B — scope to `TenantMembership`,** and first make membership real: call
  `TenantService.add_member` on login/role-grant and backfill. That is a
  multitenancy change with consequences well beyond equipment (it is the same
  decision [onboarding F5](../../reviews/new-tenant-onboarding-ux.md) parks), and it
  should not ride in on an equipment fix.

**Do not start task 3.1 until the user has chosen.** If Option B is chosen, this
wave becomes a dependency on that work and the equipment tasks reduce to the three
uncontroversial exclusions plus the escape hatch.

The rest of this file assumes **Option A**.

---

## Task 3.1 — A scoped "people of this community" read

**Where:** [`UserRepository`](../../../application/repositories/user_repository.py)
(a new method — the class is deliberately unscoped for global identity, so this one
scopes explicitly), using `application/repositories/_tenant.py`.

- Resolve the union described above in as few queries as possible — the role side
  through `UserRole.filter(tenant_id=...)`, the enrolment side through
  `TournamentPlayers` joined to this tenant's tournaments. Two queries and a
  Python union is fine; an N+1 over users is not.
- Exclude the system account and `is_active=False` **in the query**, not in the
  caller.
- Order by the same key the existing picker uses so option order does not jump
  (`username`, rendered as `preferred_name`).
- Keep `get_all` untouched — the Users tab, the match dialog and the MCP tools all
  depend on the global list, and changing it under them is a different decision
  (that is the cross-cutting theme, not this wave).

**Tests:** `tests/tenancy/` leak test — a user who belongs only to the *other*
seeded tenant never appears; `tests/services/` unit tests for system-account and
inactive exclusion, for the holder being included even when they hold no role, and
for the union not duplicating a user who is both a role-holder and an entrant.
These fail without the change.

---

## Task 3.2 — Expose it on `UserService`, not `EquipmentService`

**Where:** [`UserService`](../../../application/services/user_service.py).

Add `get_community_people(...)` (name it for the concept, not the caller). It
belongs here because the Users tab and the match dialog's "Choose any players" have
the identical leak and will want it next — and because hanging it off
`EquipmentService` would drag `FeatureFlag.EQUIPMENT`'s declared `service_modules`
gating onto a people read that has nothing to do with equipment.

No `@requires_feature`. No audit entry — it is a read.

**Docs:** [`docs/reference/services.md`](../../reference/services.md).

---

## Task 3.3 — Use it in the checkout dialog, with an honest escape hatch

**Where:** [`checkout_dialog.py`](../../../theme/dialog/checkout_dialog.py).

- Replace `UserService().get_all_users()` with the new read.
- Add the **Search all platform users** toggle (a `ui.checkbox` or `ui.toggle`
  above the select). Off by default; when switched on, refill the options from
  `get_all_users()` **minus the system account and inactive users** — the two hard
  exclusions survive the escape hatch. Label the toggle so it reads as a widening,
  not a filter: *"Include people outside this community"*.
- Default the select to the actor, as today.
- While in this file: convert its three `ui.notify(str(e), color='warning')` calls
  to `notify_error(e)` per CLAUDE.md — this is the file the audit's error-toast
  convention has not reached.

**Tests:** `tests/theme/` assertions on the dialog's option-building given a
stubbed read (system account absent; toggle widens the set). Keep them at the level
the existing theme tests work at.

---

## Task 3.4 — The same leak in the owner picker

**Where:** [`equipment_dialog.py`](../../../theme/dialog/equipment_dialog.py) — its
`owner_options` is built from the same `get_all_users()` call.

Found while planning this wave, not in the audit: the Add/Edit Asset dialog's
**Owner** select offers every platform user too, so an asset can be recorded as
owned by a stranger or by `System`. Same read, same exclusions; keep the
community-owned sentinel (`_WIZ_OWNER`) first in the list. An asset whose stored
owner falls outside the set must still display and remain saveable without silently
dropping the owner — check the edit path explicitly.

---

## Task 3.5 — Enforce only the hard rules in the service

**Where:** [`EquipmentService.checkout`](../../../application/services/equipment_service.py).

The picker is a default, not an authorization rule — but two of the three
exclusions are rules and belong in the service, which is the only place the MCP
surface, a future REST router or a Discord handler would pass through:

- reject a borrower who is the system account;
- reject a borrower who is `is_active=False`;
- **do not** reject a borrower who is merely outside the community set — that is
  exactly what the escape hatch exists for, and hard-enforcing it would break the
  venue case this wave is trying to serve.

Message wording follows the service convention (`ValueError`, user-facing, no
prefix): *"That account cannot borrow equipment."*

**Tests:** `tests/services/test_equipment_service.py` — both rejections, plus a
positive case proving a non-member *can* still be checked out to. That last test is
the one that documents the decision.

---

## Task 3.6 — Seed a user who proves the scoping

**Where:** [`scripts/seed_dev.py`](../../../scripts/seed_dev.py).

The seed already builds two tenants. Ensure at least one user exists who holds a
role in **only one** of them, and note it in the seed's console output, so the
picker's scoping is visible in the dev loop and not only in a test. Idempotent,
tenant-scoped, same style as the surrounding block.

---

## Task 3.7 — Re-measure

As `staff_user` at 390×844: open the checkout dialog and record the option count
and whether `System` is present (the audit measured **11 options, `System`
included**). Then switch the escape hatch on and record the count again. Check the
Add Asset dialog's Owner select the same way. Verify the other tenant's user
appears in neither list with the hatch off.

**Docs:** the checkout/asset-dialog rows in
[`docs/reference/frontend.md`](../../reference/frontend.md), and — when this wave
merges — strike the equipment clause from the global-`User`-picker bullet in
[`reviews/README.md`](../../reviews/README.md)'s cross-cutting themes, leaving the
Users tab and match dialog named.
