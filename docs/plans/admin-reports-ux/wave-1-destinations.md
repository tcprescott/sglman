# Wave 1 — make the destinations linkable

**Read [README.md](README.md) first.** The design decisions and the verification
loop are there and are not repeated here.

Wave 1 changes nothing an operator can see. It builds the two things wave 2
needs and cannot fake: **surfaces that accept a deep link**, and **users who are
not staff**, so the gating on wave 2's links can actually be tested.

| Task | Builds | Depends on |
|---|---|---|
| T1.1 | `cc_user` and `vc_user` in the dev seed | — |
| T1.2 | `admin_url()` + per-tab query params in `pages/admin.py` | — |
| T1.3 | Schedule tab accepts `match_id` | T1.2 |
| T1.4 | Vol. Schedule tab accepts `day` | T1.2 |
| T1.5 | Docs | T1.3, T1.4 |

---

## T1.1 — Seed a crew-coordinator-only and a volunteer-coordinator-only user

**Why.** Wave 2 renders a link only when its destination will admit the viewer,
and the Reports tab admits three different kinds of operator
([`pages/admin.py:163`](../../../pages/admin.py#L163)). `staff_user` satisfies
every predicate, so **as staff you cannot see a gating bug** — you see every
link and every one of them works. The dev seed currently grants
crew-coordination *to staff itself*
([`scripts/seed_dev.py:265`](../../../scripts/seed_dev.py#L265):
`tournament.crew_coordinators.add(staff)`) and creates no volunteer coordinator
at all ([`:195`](../../../scripts/seed_dev.py#L195) — the `role_grants` list has
no `VOLUNTEER_COORDINATOR`).

This is the cross-cutting theme the reviews already recorded — *the dev seed
cannot produce the roles that expose the worst bugs*; three audits needed a role
they had to grant by hand. Fix it once, here, because this wave is where it
first bites.

### Files

- `scripts/seed_dev.py`
- `docs/development.md` (the seeded-logins list)

### Change

Add two users to `user_specs`
([`:72`](../../../scripts/seed_dev.py#L72)), keeping the discord-id sequence:

```python
        ("100000000000000009", "cc_user",      "Crew Coordinator"),
        ("100000000000000010", "vc_user",      "Volunteer Coordinator"),
```

Grant `vc_user` the `VOLUNTEER_COORDINATOR` role in `role_grants`
([`:194`](../../../scripts/seed_dev.py#L194)) — **and nothing else**; the point
of the fixture is a coordinator with no staff grant.

`cc_user` gets **no role row at all**: crew coordination is a per-tournament
relation, not a `Role`. Add it beside the existing line:

```python
        await tournament.crew_coordinators.add(users['cc_user'])
```

Keep `staff_user` on `crew_coordinators` too — removing it would change what the
existing fixture tournament demonstrates.

Both users still need their `TenantMembership`, which the loop at
[`:187`](../../../scripts/seed_dev.py#L187) already gives every user in
`users.values()`.

### Verify

- `poetry run python scripts/seed_dev.py` twice — idempotent, no duplicate rows.
- Log in as `cc_user` at `/t/default/login`: the admin drawer shows **Schedule,
  Tournaments and Reports and nothing else**. Log in as `vc_user`: **Vol.
  Roster, Vol. Schedule, Reports**.
- Both users exist in the `second` tenant too (the seed loops over
  `TENANT_SPECS`) — confirm `vc_user`'s role row is per-tenant, not global.

### Docs

Add both to the seeded-logins list in `docs/development.md`, each with one line
saying what it is *for*: "a coordinator with no staff grant — the fixture for
checking that an admin surface gates on capability, not on staff-ness".

---

## T1.2 — One place that builds admin deep links, and tabs that receive their params

**Why.** `reports_url()`
([`shared.py:63`](../../../pages/admin_tabs/reports/shared.py#L63)) already
builds `/admin/reports?…` and the admin page already declares the reports'
params and forwards them to the Reports tab as `reports_kwargs`
([`pages/admin.py:38`](../../../pages/admin.py#L38),
[`:100`](../../../pages/admin.py#L100),
[`:163`](../../../pages/admin.py#L163)). No other tab receives a single query
param: `admin_schedule_page(can_crud)` and `admin_volunteers_page()` take none.
Wave 2 has nowhere to link *to* until that changes.

### Files

- `pages/admin_tabs/links.py` (new)
- `pages/admin.py`
- `pages/admin_tabs/reports/shared.py`

### Change 1 — the helper

New module `pages/admin_tabs/links.py`. It is presentation-only and imports
nothing from `application/`:

```python
"""URLs into the admin tabs.

Section slugs are path segments (``/admin/schedule``); everything a surface
needs to focus on arrives as a query param, the same way the Reports tab has
always taken its filters. Root-relative on purpose: NiceGUI derives the client
prefix from the page's root_path, so a bare ``/admin/…`` resolves inside
``/t/<slug>`` — see middleware/tenant.py.
"""
```

with one function, `admin_url(section: str, **params) -> str`, using the same
`None`/`''`-dropping and `date`/`datetime` `isoformat()` normalisation
`reports_url` performs (lines 68–78). Section slugs come from the tab labels
lower-cased and hyphenated by `BaseLayout`; **read `theme/base.py` and confirm
the slug for "Vol. Schedule" rather than guessing it** — the link is worthless
if the slug is wrong, and this is the one detail in the wave that cannot be
derived from the report code.

Then re-express `reports_url` in terms of it (`admin_url('reports', report=…,
**params)`) so there is one implementation of the parameter rules. Keep the name
`reports_url` and its signature: eight report modules call it.

### Change 2 — the params

In `admin_dashboard_page`
([`pages/admin.py:37`](../../../pages/admin.py#L37)) add two query params to the
signature, beside the existing `report`/`start`/`end`/… set:

```python
        match_id: int = None,
        day: str = None,
```

`state` already exists and is already forwarded to Reports; **do not reuse it**
for the board's state filter — that would make one param mean two things
depending on which tab reads it. If wave 2 wants to preset the board's state
filter, add `board_state` in that wave and say so.

Then hand each tab its own kwargs the way Reports is handed `reports_kwargs`:

```python
        schedule_kwargs = {'can_crud': can_crud, 'match_id': match_id}
        ...
            tabs.append({'label': 'Schedule', 'icon': 'schedule', 'group': 'Operations',
                         'content': (admin_schedule_page, (), schedule_kwargs)})
        ...
            tabs.append({'label': 'Vol. Schedule', 'icon': 'event_available', 'group': 'Community',
                         'content': (admin_volunteers_page, (), {'day': day})})
```

Leave every other tab's entry alone.

### Watch for

Every tab panel renders eagerly on an `/admin` load — the comment at
[`reports/__init__.py:38`](../../../pages/admin_tabs/reports/__init__.py#L38)
records it. So `?match_id=412` is passed to the Schedule tab **even when the
operator opened `/admin/reports`**, and T1.3's focus must be inert unless the
Schedule section is the active one *or* must be cheap enough not to matter. The
simplest correct answer is the latter: a filtered query is not more expensive
than an unfiltered one. Do not add a "which section is active" check inside a
tab body to work around this.

### Verify

`poetry run pytest` (nothing should reference the removed duplication), then
load `/t/default/admin/reports?report=crew&match_id=1&day=2026-07-29` and
confirm the page still renders and no tab throws on the unknown-to-it params.

---

## T1.3 — The Schedule board accepts `?match_id=`

**Why.** Four of the nine reports name a match id and cannot get you to it. The
board's data source is a single callable —
[`admin_schedule.py:40`](../../../pages/admin_tabs/admin_schedule.py#L40):

```python
        def get_query():
            return Match.filter(tenant_id=require_tenant_id())
```

so focusing the board is a one-line narrowing of that query plus a way out of
it. **Do not touch `MatchTableView`'s filter machinery** — its three filters are
session-persisted per board (`storage_key='admin_schedule'`,
[`:110`](../../../pages/admin_tabs/admin_schedule.py#L110)) and a deep link must
not permanently rewrite the operator's stored filters.

### Files

- `pages/admin_tabs/admin_schedule.py`

### Change

`def admin_schedule_page(can_crud: bool = True, match_id: int = None) -> None:`

- Narrow `get_query()` to `.filter(id=match_id)` when `match_id` is set.
- Above the review queue, when focused, render a chip that says what is
  happening and offers the way out — `Showing match #412 only` with a
  **Show all matches** button navigating to `admin_url('schedule')`. Without
  that, an operator who follows a link is stuck on a one-row board and will
  reasonably think the board is broken.
- The default state filter (`['Scheduled', 'Checked In', 'Started',
  'Finished']`, [`:111`](../../../pages/admin_tabs/admin_schedule.py#L111))
  hides a **Confirmed** match. A report row for a confirmed match would land on
  an empty board — when `match_id` is set, pass `default_state_filter=None` (or
  the full set) so the focused match is always visible. Check what
  `MatchTableView` does with `None` before choosing;
  `_stored_or_default_states` ([`theme/tables/match.py:114`](../../../theme/tables/match.py#L114))
  is the code that decides.
- A `match_id` from another tenant, or one that does not exist, must render the
  empty board with the chip — **not** an error. `require_tenant_id()` in the
  query already makes cross-tenant ids return nothing; confirm it, don't assume
  it.

### Verify

- `/t/default/admin/schedule?match_id=<a Confirmed match>` shows exactly that
  match, with the chip; **Show all matches** restores the board with the
  operator's stored filters intact (change a filter first, follow a focused
  link, come back — the filter must survive).
- `?match_id=999999` and a `second`-tenant match id: empty board, chip, no
  traceback in `/tmp/app.log`.
- As `cc_user` (T1.1): the board opens and the row actions are whatever
  `can_crud` already decides — this task changes no authorization.
- 390 px: the chip does not push the table off-screen.

---

## T1.4 — Vol. Schedule accepts `?day=`

**Why.** The volunteers report's one actionable line is *"57 shift(s) need 57
more volunteer(s)"*, and the fix is per-day on Admin → Vol. Schedule, which
opens on the **first** event day regardless
([`admin_volunteers.py:54`](../../../pages/admin_tabs/admin_volunteers.py#L54)):

```python
    state = {'day': day_options[0] if day_options else event_start.isoformat()}
```

### Files

- `pages/admin_tabs/admin_volunteers.py`

### Change

`async def admin_volunteers_page(day: str = None) -> None:`, and seed
`state['day']` from `day` **only when it is one of `day_options`** — an
out-of-window or malformed date falls back to the current default silently. The
`day_select` at [`:73`](../../../pages/admin_tabs/admin_volunteers.py#L73) binds
to `state['day']`, so it will show the linked day with no further change.

Nothing else moves: the permission check at
[`:37`](../../../pages/admin_tabs/admin_volunteers.py#L37) already refuses a
viewer who cannot manage volunteers, and it must keep running **before** the day
is applied.

### Verify

- `/t/default/admin/vol-schedule?day=<second event day>` (slug per T1.2) opens
  on that day; `?day=1999-01-01` and `?day=banana` open on the default day with
  no error.
- As `vc_user`: reachable. As `cc_user`: still refused — a deep link is not a
  permission.

---

## T1.5 — Document what the tabs now accept

**Files:** `docs/features/admin-reports.md`, `docs/reference/frontend.md`.

Add a short table of the admin tabs' query params — `report`, `start`, `end`,
`tournament_id`, … for Reports; `match_id` for Schedule; `day` for Vol.
Schedule — and one sentence naming `pages/admin_tabs/links.py` as the only place
that builds them. Do not restate the parameter-normalisation rules; point at the
module.
