# New tenant onboarding UX — evaluation

**Scope:** day one for a new community — `/platform`'s tenant creation
([`pages/platform.py`](../../pages/platform.py)), the zero state of every admin
and home surface under the new `/t/<slug>`, the path from an empty community to
its first schedulable match, and what a role-less platform user sees in it.

**Method:** created a real tenant (`audit-third`, "Audit Third Community") through
`/platform` as `super_admin` on the running app, then inventoried its empty state
tab by tab, drove the first-match path counting interactions, and re-checked every
surface as `player_two` (no roles in the new tenant). The tenant is left in the dev
DB. Every number below is measured.

**Headline:** creating a community takes four fields and works. What follows is
the problem: the new community's **first screen is the one action that cannot yet
succeed** (Create Match, with an empty tournament dropdown), the only
tournament-centric entrant surface is read-only, and the fastest route to a
working match runs through "Choose any players", which lists **every user on the
platform** — including the `System` account — and silently enrols whoever you
pick. Nothing anywhere sequences the setup, and there is no membership boundary:
the moment the community has a match, every logged-in user of every other
community can see it and sign up as crew.

---

## The measured shape

Creating the tenant: one dialog, four fields — `Name`, `Slug`,
`Custom domain (optional)`, `Discord guild id (optional)` — then `Tenant created`.
The new row's only actions are **Edit** and **Features**. Nothing is created with
it: no first admin, no default position, no stream room, no starter tournament.

Empty community, first match:

| Step | Interactions | What happened |
|---|---:|---|
| Land on `/admin` → **Create Match** (what the page offers first) | 1 | Tournament dropdown opens **no menu at all** (0 options); Create → *"Please fill required field(s): Tournament."* |
| Admin → Tournaments → Add Tournament → name it → save | 3 | Dialog is **21 inputs, 4 selects, 5 checkboxes, 1,730 px tall**; only the name is required |
| Back to Create Match, pick the tournament, open Players | 3 | **0 player options** — nobody is enrolled |
| Tick **Choose any players**, reopen Players | 2 | **11 options** — every `User` row on the platform, `System` included |
| Pick two, Create | 3 | *"Match created successfully"* — with `System` as a player |
| **Total after the dead end** | **13** | |

### The empty-state inventory

Every admin tab in the new tenant returned HTTP 200 — nothing crashed on zero
data. What each says:

| Tab | Rows | Zero state |
|---|---:|---|
| Schedule | 0 | `No matches to show yet.` + a **Create Match** button that cannot work yet |
| Users | **11** | *"Everyone in this community and the roles they hold"* — the whole platform's users (F2) |
| Tournaments | 0 | Caption explains the concept; `Add Tournament` present |
| Stream Rooms | 0 | `No data available` (bare Quasar default) |
| Reports | 0 | KPI cards render `0 / 60`, `no scheduled matches in window` — graceful |
| Features | — | `Your tier: Default (default)` + per-feature descriptions. Best-explained tab in the app |
| Settings | — | Blank fields with derivation notes (*"Leave blank to derive the event window from scheduled match times"*) |
| Service Health | 0 | `No dependencies to report.` |
| Discord Roles | 0 | `No Discord server is connected to this community.` + what connecting requires + **Connect Discord server** — the model empty state |
| Webhooks | 6 | The 6 rows are the static event-reference table, not webhooks |
| Feedback | 0 | `No data available` |
| Appearance | — | Presets, with a WCAG-AA note |

Home tabs (`/home/schedule`, `/on-air`, `/profile`, `/player`) all render; two use
the `no_data_slot` empty state, one says `No matches scheduled for this date.`

Gated surfaces behave correctly: `/qualifiers` and `/volunteer` both render
**404 — "This feature is not enabled for this community."** (`/brackets` and
`/equipment` are not routes at any tenant — the bare paths 404 on `default` too.)

---

## Root causes

### RC1 — Tenant creation makes a row, not a community

`create_tenant` validates the name, slug and domain, writes one `Tenant`, clears
the cache and audits
([`tenant_service.py:206-233`](../../application/services/tenant_service.py#L206)).
Everything a community needs to function — a staff grant, at least one tournament,
a stage, an event window — is left to whoever opens `/admin` next, in whatever
order they guess. There is no setup checklist, no ordering, no "next step" hint,
and the drawer arrives at full size: **19 items** including Presets, Randomizer
Keys, Discord Events, Webhooks and Service Health, before the community has a
single tournament.

### RC2 — Every surface is designed for a populated tenant, so the first screen is the least useful one

`/admin` defaults to Schedule Management, whose primary control is Create Match,
whose first field can only be satisfied by a tournament that does not exist. The
same mismatch documented as
[match-operations-ux F4](match-operations-ux.md#f4--critical--two-thirds-of-the-tournament-dropdown-cannot-be-scheduled-and-you-find-out-after-submitting)
appears here in its sharpest form: on day one the dropdown is not merely
two-thirds dead, it is empty, and it opens no menu at all rather than saying so.

### RC3 — Enrolment has no tournament-centric surface

The Tournaments tab's own caption says *"click a name to edit, or a player count
to manage entrants"*, and the dialog behind that link
([`tournament_players_dialog.py`](../../theme/dialog/tournament_players_dialog.py))
is **26 lines of read-only list plus a Close button** — no add, no remove. Actual
enrolment happens in three other places: the per-user edit dialog
(`update_user_tournament_registrations`), the player's own Profile tab, or as an
invisible side effect of scheduling a match with "Choose any players"
([match-operations-ux F8](match-operations-ux.md#f8--minor--choose-any-players-silently-enrolls-someone-in-the-tournament)).
For a new community with nobody enrolled, the third is the only one that is
discoverable from where they are standing.

### RC4 — Identity is global and membership is not gated, so a new community is public to the platform on creation

This is documented as deliberate —
[multitenancy.md](../features/multitenancy.md) records that authorization is
tenant-scoped rather than membership-gated because *"the app has no self-serve or
invite enrollment path, so such a gate would lock out every new user"* — and
`TenantMembership` exists to record who belongs. The onboarding consequence has
not been looked at: measured, `player_two` (no roles in `audit-third`, never
invited) loaded the new community's home schedule, saw its first match with both
players' names, and was offered **Sign Up** as commentator and tracker.

---

## Findings, ranked

### F1 — Critical · Day one starts on a dead end

Measured: the first thing `/admin` offers is Create Match; its Tournament select
opens an empty menu (no "no tournaments yet" row, no hint); Create answers
*"Please fill required field(s): Tournament."* A first-time admin's opening
interaction with the product is a control that cannot succeed and does not say
why. The fix is small and local — an empty select should say what is missing and
link to where to make it — but the sequencing problem behind it (RC1) is the real
one: nothing tells a new admin that tournament → stage → enrolment → match is the
order.

### F2 — Critical · A brand-new community's Users tab lists every user on the platform

Measured: 11 rows in a community created 30 seconds earlier, under the caption
*"Everyone in this community and the roles they hold."* The query is
`User.all()` ([`admin_users.py:37-49`](../../pages/admin_tabs/admin_users.py#L37)),
unscoped by design because `User` is a global identity — but the caption promises
community scoping, the rows are clickable into an edit dialog that writes
**global** profile fields (display name, pronouns), and `TenantMembership` exists
precisely to answer "who belongs here". Whether the list should be scoped is a
product decision; the caption is wrong either way, and on day one the effect is a
new community's first admin screen showing eleven strangers.

### F3 — Major · The path of least resistance enrols arbitrary users, including `System`

Measured: with nothing enrolled, "Choose any players" turns the Players select
from 0 options into 11 — the same global list as F2, including the `System`
service account, which the run used to create the community's first match. The
side effect (silent enrolment into the tournament) is invisible here as everywhere,
and RC3 means there is no better route on offer.

### F4 — Major · The first form a new community meets is the largest in the app

Add Tournament measures 1,730 px, 21 inputs, 4 selects, 5 checkboxes — seed
generator, seed preset, bracket URL, rules URL, format, triforce-text access
message, durations, players per match, team size, staff-administered, tournament
days. Exactly one field is required. Nothing distinguishes "fill this now" from
"come back to this when you care", so the cheapest correct action (type a name,
save) looks like the riskiest one.

### F5 — Major · A new community is visible, and joinable, to every logged-in platform user

RC4, measured: a user with no roles and no invitation reached the new community's
home schedule and was offered crew signup on its first match. For a single-operator
deployment this is invisible; for the multi-community platform the code is built
for, "create a community" currently means "publish a community". The pieces to
change it (`TenantMembership`, the picker) already exist — what is missing is a
decision about what a new tenant's default visibility should be.

### F6 — Minor · Two zero states are bare Quasar defaults

Stream Rooms and Feedback show `No data available`; the codebase has
[`theme/empty_state.py`](../../theme/empty_state.py) and uses it well elsewhere
(`No matches to show yet.`). Discord Roles shows what a good one looks like:
what is missing, what connecting requires, and the button that does it.

### F7 — Minor · Nothing in the tenant row says the community is unusable yet

`/platform`'s row shows name, slug, domain, guild, active, Edit, Features. A
super-admin who provisions ten communities cannot tell from that table which of
them have a staff member, a tournament or a stage — i.e. which ones are actually
set up. The data is one query away and the row has space.

---

## What works

- **Nothing broke on zero data.** Every admin tab and home tab returned 200 with a
  populated tenant's layout and empty tables — including Reports, which renders its
  KPI cards as `0 / 60` with `no scheduled matches in window` rather than blank
  axes. That is the hard part of a zero state and it was already right.
- **Feature gating explains itself.** `/qualifiers` and `/volunteer` say *"This
  feature is not enabled for this community"* rather than a generic 404, and the
  Features tab explains the two-tier model in one sentence: *"Which features are
  available to your community is set by a platform administrator (your tier); you
  control whether each available one is on."*
- **The Discord Roles empty state** — the template every other zero state should
  copy.
- **Settings' derivation notes** — *"Leave blank to derive the event window from
  scheduled match times"*, *"Blank uses the default of 60"*. A new admin can skip
  the whole page safely and knows it.
- **Slug and domain validation** on create, with the shared-guild hint on the
  Discord field.

## Not covered

The custom-domain path (no second host in dev), `scripts/seed_tenant.py`'s
behaviour compared with the UI, feature-flag *group* assignment from `/platform`,
and Discord server connection (needs a real guild).
