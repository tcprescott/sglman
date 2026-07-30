# New tenant onboarding — implementation plan

Turn "create a tenant" from *writing one row* into *provisioning a community*:
one that has a first admin, tells its admin what to do next, knows who belongs
to it, and is not published to the whole platform the moment it exists.

**Read this file completely before starting any task.** It carries the evidence,
the design decisions and the ground rules that the wave files do not repeat.

Source: [`docs/reviews/new-tenant-onboarding-ux.md`](../../reviews/new-tenant-onboarding-ux.md).
Every measurement quoted below is from that audit unless marked otherwise; the
audit stays in the tree until the last wave lands, then is deleted with it.

## Wave files

| Wave | File | Theme | Migration? |
|---|---|---|---|
| 1 | [wave-1-provision-and-sequence.md](wave-1-provision-and-sequence.md) | A tenant gets a first admin and a derived setup checklist; the dead end goes away | no |
| 2 | [wave-2-membership-is-real.md](wave-2-membership-is-real.md) | `TenantMembership` becomes the answer to "who is in this community", and every per-community picker uses it | no |
| 3 | [wave-3-enrolment.md](wave-3-enrolment.md) | Enrolment gets a tournament-centric surface; the Add Tournament wall is broken up | no |
| 4 | [wave-4-membership-gate.md](wave-4-membership-gate.md) | Membership gates the tenant, with the join path that makes the gate safe | **yes** |

Waves 1–3 change no authorization. **You can stop after wave 2** and both
Critical findings are fixed. Wave 4 is the one that changes who can see what,
and it is deliberately last — see design decision 2.

Do not start wave N+1 until wave N is merged.

## The evidence this exists to fix

The audit created a real tenant through `/platform` and counted. The headline:
**a new community's first screen is the one action that cannot yet succeed.**
`/admin` opens on Schedule Management, whose primary control is Create Match,
whose Tournament select opens *no menu at all* — 0 options, no "none yet" row —
and answers *"Please fill required field(s): Tournament."* Thirteen interactions
later you have a match, by way of "Choose any players", which lists every `User`
row on the platform and enrolled the `System` service account as a player.

Three things say the concept "a community was provisioned" is missing rather
than merely unpolished:

**The one method that would create a first admin is wired to nothing.**
`TenantService.bootstrap_staff` grants STAFF + membership in a new tenant, is
super-admin gated, and is covered by
`tests/services/test_tenant_service.py::test_bootstrap_staff_is_per_tenant`.
Grepped on this branch, it has **no caller outside that test** — `/platform`'s
tenant row offers only Edit and Features. So the documented way to stand up a
community is `scripts/seed_tenant.py --operator-discord-id`, a shell script,
and the UI path simply does not exist. This is the reviews' recurring
["capabilities nobody wired are invisible"](../../reviews/README.md#cross-cutting-themes)
theme, in the place where it costs the most.

**Membership exists, is populated, and is read by nothing.**
`models/tenant.py`'s `TenantMembership` docstring already says it is *"what the
auth layer checks to decide whether an authenticated user may see a tenant at
all"*. It has a per-tenant index added for member enumeration, a full repository
(`TenantMembershipRepository.list_for_tenant` and friends), and a migration
(`20_20260712000000_multitenancy.py`) that backfilled a row per existing user.
Nothing in `pages/`, `theme/`, `api/` or `mcpserver/` reads it. The auth layer
comment at [`middleware/auth.py:162-168`](../../../middleware/auth.py#L162)
explains the gap honestly: there is no gate *"since the app has no
self-serve/invite enrollment path and it would lock out new users"*.

**Every per-community person-picker is the global user table.** The audit named
three; grepped, `UserService.get_all_users()` (which is
`User.all().order_by('username')`, unscoped —
[`user_repository.py:46-65`](../../../application/repositories/user_repository.py#L46))
backs **seven** call sites, five of them per-community pickers:

| Site | What it offers |
|---|---|
| [`pages/admin_tabs/admin_users.py:40`](../../../pages/admin_tabs/admin_users.py#L37) | The Users tab, under the caption *"Everyone in this community"* |
| [`theme/dialog/match_dialog.py:374,640`](../../../theme/dialog/match_dialog.py#L374) | Commentators, Trackers, and Players under "Choose any players" |
| [`theme/dialog/checkout_dialog.py:28`](../../../theme/dialog/checkout_dialog.py#L28) | The equipment borrower |
| [`theme/dialog/equipment_dialog.py:33`](../../../theme/dialog/equipment_dialog.py#L33) | The equipment owner/assignee |
| [`pages/admin_tabs/admin_brackets/manage.py:37`](../../../pages/admin_tabs/admin_brackets/manage.py#L37) | Bracket entrants |
| [`api/routers/users.py:56`](../../../api/routers/users.py#L56) | `GET /users`, inside a tenant-scoped token context |
| [`mcpserver/tools/people.py:56`](../../../mcpserver/tools/people.py#L56) | `list_users`, likewise |

The last two matter more than the audit could see from the browser: a
tenant-scoped API token and an MCP session both enumerate every user on the
platform. Wave 2 is where that stops.

## Design decisions

Fixed, and agreed with the maintainer before this plan was written. **If a task
seems to contradict one of these, the task is wrong — stop and ask.**

1. **Membership is the answer to "who belongs here", not a new
   `Tenant.is_public` switch.** A per-tenant public/private setting was
   considered and rejected: it would leave two access paths to maintain forever,
   and the model that answers the question already exists and is already
   populated. `TenantMembership` becomes load-bearing.

2. **The gate arrives last, and only after membership is obtainable.** The
   reason `middleware/auth.py` has no membership gate today is correct as
   written — flipping it before there is any way to *become* a member locks out
   every user of every existing community. Wave 2 makes membership visible and
   manageable, wave 4 adds the join path, and only then does the gate close.
   **Wave 4's first task is the backfill audit, not the gate.**

3. **The checklist is derived, never stored.** No `setup_complete` column, no
   dismissal flag, no per-step state. It is one query answering "does this
   tenant have a staff member / a tournament / an enrolled player / an event
   window", and it disappears when the answers are all yes. Storing progress
   invents a second source of truth that drifts the first time someone deletes
   a tournament.

4. **No per-tenant feature flag.** Onboarding is infrastructure every tenant
   passes through *before* it could enable anything; a flag would have to be on
   for the tenant that most needs it. Flags exist for deliberately-gated
   subsystems, and this is not one. Nothing in these waves registers a
   `FeatureFlag` or calls `requires_feature`.

5. **Identity stays global.** `User` is not getting a `tenant` FK and the
   per-user edit dialog keeps writing global profile fields. Membership is the
   join table; scoping a picker means joining through it, never duplicating a
   user per community.

6. **`create_tenant` still writes exactly one row.** Provisioning starter
   content (a default tournament, a stream room, an event window) was considered
   and rejected: every community would begin with rows it must identify and
   delete, and the checklist teaches the ordering more honestly than fixtures
   do. What creation gains in wave 1 is a *first admin*, which is not content.

7. **Do not scope `UserRepository.get_all`.** Add a member-scoped query beside
   it and convert callers one at a time. The global list has legitimate
   platform-level callers (wave 1's staff picker is one), and silently changing
   what an existing method returns is how a leak becomes a lockout.

## Ground rules

Everything in [CLAUDE.md](../../../CLAUDE.md) applies. The parts these tasks hit:

**Three-layer pattern.** `enforce_architecture.py` blocks violations at write
time, and classifies `api/`, `discordbot/` and `mcpserver/` as presentation —
so the two entry-surface call sites in the evidence table must route their fix
through a *service* method, never `application.repositories`.

**Tenant scoping.** `TenantMembership` is one of two models in
`check_tenant_scoping.py`'s `EXEMPT_MODELS` — it is cross-tenant by nature and
its reads are always membership checks. That exemption is why a membership query
looks unscoped and is still correct; do not "fix" it with `scoped(...)`.
`tests/tenancy/test_leak_test_coverage.py` records the same reasoning. Every
*other* query these waves add is scoped normally.

**Authorization.** `require_tenant_id()` raising is the safety net. Wave 4
changes `_tenant_page`, which every tenant page shares — the blast radius is the
whole app, and `SUPER_ADMIN` must bypass the new gate exactly as it bypasses the
role gate today.

**Audit + events.** `AuditService.write_and_publish`;
`check_dry_regressions.py` blocks a hand-rolled `write_log` + `event_bus.publish`
pair. `AuditActions` already has `TENANT_CREATED` / `TENANT_UPDATED`
([`audit_service.py:314`](../../../application/services/audit_service.py#L314));
there are **no** `EventType` members for tenancy yet, so the waves that need them
add to both `EventType` and `EventType.ALL` (`check_event_types.py` enforces the
pair). `EventType` is an external contract — add, never rename.

**NiceGUI.** `background_tasks.create`, never `asyncio.create_task`. Capture
`context.client` before any background task that calls `ui.*`. Every new
`ui.table` needs `enable_mobile_grid(...)` or a `# mobile-grid: exempt` comment
— `check_table_grid.py` enforces it.

**Dev seed.** `scripts/seed_dev.py` already creates a `TenantMembership` per
seeded user ([line 188](../../../scripts/seed_dev.py#L188)), which is why the
existing tenants will look right immediately — and exactly why the seed must
grow a **half-provisioned tenant** in wave 1. A checklist nobody can see in a
half-done state is a checklist nobody can review. `check_seed_coverage.py`
enforces this for new models (wave 4's).

**File length.** `check_file_length.py` advises over 800 lines.
`pages/platform.py` is 709 and wave 1 adds to it — extract rather than push it
over.

## Verification loop

```bash
bash scripts/setup_env.sh                      # once
nohup ./start.sh dev > /tmp/app.log 2>&1 &     # wait for "Application startup complete"
poetry run python scripts/seed_dev.py
```

Mock-Discord logins at `/t/<slug>/login`: `staff_user`, `proctor_user`,
`player_one`…`player_four`. Pages live under `/t/<slug>/…`; a bare `/admin`
404s. Chromium is at `/opt/pw-browsers` — **never run `playwright install`**.
`scripts/ui_smoke.js` is a config-driven harness; read its header comment.

**This plan's verification is different from most: the subject is a tenant that
does not exist yet.** Every wave must be checked against a *freshly created*
community, not the seeded `default` one — the seed's tenants are fully populated
and will pass a checklist that a real new tenant fails. The loop:

1. Log in as a super-admin, create a tenant at `/platform` (the audit used
   `audit-third` / "Audit Third Community"; reuse it or make another).
2. Drive `/t/<new-slug>/admin` as its first admin **and** as a platform user
   with no roles in it (`player_two` is the audit's control) — the second is
   what catches the visibility findings.
3. Re-measure at 1500px **and** 390×844.

```bash
poetry run pytest                       # whole suite, parallel
poetry run pytest -n0 -k tenant         # serial, for -s / pdb
poetry run pytest tests/tenancy/        # the isolation suite, every wave
scripts/ui_flag_sweep.sh                # flags-off sweep
```

## Definition of done for every task

1. Implemented in the files named, at the layer named.
2. `poetry run pytest` green, `tests/tenancy/` included.
3. The task's own tests exist **and fail without the change** — say so if a test
   cannot meet that bar and why.
4. The affected surfaces render at both widths **on a freshly created tenant**,
   verified by screenshot, with no new console errors.
5. Docs named in the task updated.
6. Committed with a message describing the behaviour change, not the diff.

If a task turns out to be wrong or blocked, **finish the rest of its wave and
say explicitly what you left out and why.** Do not silently narrow scope.

## When this directory is finished

`docs/README.md`: *design records are not kept after they ship.* Delete each
wave file as its wave merges. When the last one lands, delete this directory and
[`docs/reviews/new-tenant-onboarding-ux.md`](../../reviews/new-tenant-onboarding-ux.md)
together, remove both rows from the "Work in flight" tables, and make sure the
behaviour lives in the feature docs — principally
[`docs/features/multitenancy.md`](../../features/multitenancy.md) (membership as
a gate, the join path, provisioning) and
[`docs/reference/authentication.md`](../../reference/authentication.md) (what
`_tenant_page` now checks). Two cross-cutting entries in
[`docs/reviews/README.md`](../../reviews/README.md) — the global-`User`-leak
theme and the invisible-capabilities theme — are partly discharged here; trim
them to what still stands rather than deleting them wholesale.
