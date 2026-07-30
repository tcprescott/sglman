# Brief — New tenant onboarding UX (day one for a new community)

Scope, method and leads for an audit nobody has run yet. Leads below are
unverified suspicions from reading the code; the audit confirms or refutes each
one against the running app.

## Scope

Everything between "a super-admin creates a community" and "that community's staff
can run their first match":

- [`pages/platform.py`](../../../pages/platform.py) — tenant CRUD, the create
  dialog ([`:332`](../../../pages/platform.py#L332)), feature-flag groups, bot
  grants.
- The new tenant's own first render: `/t/<slug>/`, `/t/<slug>/admin` and every tab
  in it with zero rows.
- The setup path: granting the first roles, creating a tournament, a stream room,
  enrolling players, turning features on
  ([`admin_features.py`](../../../pages/admin_tabs/admin_features.py)),
  `admin_settings` and `admin_theme`.
- The empty-state vocabulary: [`theme/empty_state.py`](../../../theme/empty_state.py)
  and `no_data_slot`.
- [`scripts/seed_tenant.py`](../../../scripts/seed_tenant.py) — what it does that
  the UI does not.

## Why this one

The app is multitenant and
[current-state.md](../../current-state.md) lists multitenancy as stable in
production, but every audit and every dev loop has run against `default` and
`second` — tenants the seed script fully populated. **Nobody has looked at the
zero state.** It is also the cheapest audit on the list: no complex flow to drive,
just create a community and write down everything that is empty, missing, or
undiscoverable. If Wizzrobe is meant to host communities beyond SGL, this is the
first hour of their experience.

## What to measure

1. **Create a community through `/platform`** as `super_admin` and record what the
   create dialog asks for versus what a working tenant needs. Then log in as a
   fresh staff user of that tenant.
2. **Screenshot every admin tab at zero rows** and transcribe each empty state.
   Classify each as: says what this is for / says how to make the first one /
   says nothing. Do the same for the tenant's home tabs.
3. **Count the steps to a first schedulable match.** Roles granted, tournament
   created, players enrolled, stream room created, features enabled — the whole
   chain, with the interaction count and the order a first-time admin would have
   to discover it in. Note every point where a surface silently depends on
   something not yet created (lead: the tournament→players trap in
   [match-operations-ux F4](../match-operations-ux.md#f4--critical--two-thirds-of-the-tournament-dropdown-cannot-be-scheduled-and-you-find-out-after-submitting)
   is exactly this class of failure, on a populated tenant).
4. **Feature flags at defaults.** Establish what a brand-new tenant's live flag set
   actually is (availability derives from its group/tier; ungrouped falls back to
   the default group — see
   [features/feature-flags.md](../../features/feature-flags.md)), then check
   whether the admin can tell the difference between "this feature is off",
   "this feature is not available to your community" and "this feature is broken".
5. **The community picker and the bare host.** `/` is the picker, not a tenant
   home. Measure what a signed-out visitor sees, and what a signed-in member of one
   community sees.
6. **Custom domain path**, at least on paper: what changes for a tenant reached by
   its own domain rather than `/t/<slug>` (this is also where identity linking gets
   interesting — see
   [planned/identity-linking-ux.md](identity-linking-ux.md)).
7. **Mobile, 390×844**, for the first-run path specifically.

## Leads to verify

- The create dialog collects name and slug (plus domain / guild id on edit). Check
  whether anything bootstraps the new tenant: a first STAFF grant, a default
  feature group, a stream room, anything. If the answer is "the super-admin must
  then do N manual steps", that N is the finding.
- `seed_tenant.py` exists as a script. If it does setup work the UI cannot, that
  is the same signal the bracket audit found in `seed_brackets.py` — the script
  composing what the UI refuses to.
- Check whether a tenant with no members can be reached at all, and what its
  `/admin` does for a super-admin who holds no role in it (`is_staff` is
  staff-equivalent for super-admins — verify that claim holds on an empty tenant).
- Look for surfaces that assume at least one row: charts with no data, filters with
  empty option lists, reports over an empty date range, `require_tenant_id()`
  paths reached before anything exists.

## Fixtures and roles

Do **not** reuse `default`/`second`. Create a third tenant live, through the UI,
as `super_admin`, and drive it as a newly-granted STAFF user. Leaving the tenant
behind in the dev DB is fine; note it in the write-up.

## Deliverable

`docs/reviews/new-tenant-onboarding-ux.md`. Expect the findings to be mostly copy
and sequencing rather than defects — that is fine, and the empty-state inventory
table is the valuable artifact. If the audit concludes the flow needs a guided
setup surface, sketch it, but do not build it in the same pass.
