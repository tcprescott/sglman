# Wave 1 — a first admin, and a sequence to follow

**Read [README.md](README.md) first.**

No migration, no authorization change, nothing removed. At the end of this wave
a super-admin can grant a new community its first admin from `/platform` instead
of a shell script, that admin lands on a checklist instead of a dead control,
and the platform table says which communities are actually set up.

Fixes audit findings **F1** (dead end), **F6** (bare zero states), **F7** (no
readiness signal), and root causes **RC1** / **RC2**.

| Task | Touches | Size |
|---|---|---|
| T1.1 | `/platform` → the first-admin dialog (wires `bootstrap_staff`) | medium |
| T1.2 | `TenantSetupService` — the derived checklist | medium |
| T1.3 | The checklist panel, and what `/admin` opens on | medium |
| T1.4 | The empty tournament select | small |
| T1.5 | `/platform`'s readiness column | small |
| T1.6 | Two bare zero states | small |
| T1.7 | A half-provisioned tenant in the dev seed | small |
| T1.8 | Docs | small |

---

## T1.1 — Wire the first-admin grant to `/platform`

### Why this is first

`TenantService.bootstrap_staff`
([`tenant_service.py:281-296`](../../../application/services/tenant_service.py#L281))
already does exactly the right thing — super-admin gate, membership, STAFF
inside `tenant_scope(tenant_id)`, an audit row carrying `bootstrap: True` — and
**has no caller outside its test.** Until it has a button, "create a community"
cannot produce a community anyone can administer, and every task below is
describing a screen nobody can reach.

### Files

- `pages/platform.py` (the tenant row's action slots — desktop **and** the
  `item` grid slot, both at [lines 104-139](../../../pages/platform.py#L104))
- `application/services/tenant_service.py` (one new read method)

### The trap: `/platform` has no tenant context

The module docstring says CRUD here *"runs with no tenant context … so they pass
explicit ids to the repositories rather than relying on the ambient tenant."*
That applies to reads too. A dialog that lists the tenant's current staff cannot
call `AuthService.get_roles` or reach `UserRoleRepository` directly — the first
resolves roles in the *ambient* tenant (none) and the second is a repository,
which `enforce_architecture.py` forbids `pages/` from importing.

Add the read to `TenantService`, beside `bootstrap_staff`, and let it own the
scope:

```python
    @staticmethod
    async def list_staff(actor: User, tenant_id: int) -> List[User]:
        """Who holds STAFF in a tenant, read from the platform surface.

        Wraps ``tenant_scope`` because the role tables are scoped and
        ``/platform`` has no ambient tenant — the same reason
        ``bootstrap_staff`` does.
        """
        from application.tenant_context import tenant_scope

        await AuthService.ensure_super_admin(actor)
        with tenant_scope(tenant_id):
            return await UserRoleRepository.list_users_with_role(Role.STAFF)
```

Check whether `UserRoleRepository` already has that query before adding one; if
it does not, add it there, not in the service.

### The dialog

A third action on the tenant row — **Admins** — beside Edit and Features. It
lists current staff (or *"No admins yet — this community cannot be
administered."*), offers a user select, and grants.

The select here is the **global** user list, and that is correct: a super-admin
is choosing from every account on the platform precisely because the target
tenant has no members yet. This is the legitimate caller design decision 7
protects. Do not convert it in wave 2.

Grant, refresh, `ui.notify('Granted STAFF in <name>', color='positive')`. Catch
`ValueError` / `PermissionError` and notify at `color='warning'`, matching
`_open_create_dialog`'s shape at
[`platform.py:352`](../../../pages/platform.py#L352).

**Offer it at the end of creation too.** `_open_create_dialog`'s `submit()`
currently closes and refreshes; have it open the Admins dialog for the tenant it
just made. Creating a community and immediately being asked who runs it is the
whole point of the wave, and it costs three lines.

### File length

`pages/platform.py` is 709 lines and `check_file_length.py` advises over 800.
Put the dialog in a new module rather than inline — the file already has five
`_open_*_dialog` functions and this is the natural place to start splitting.

### Tests

`tests/services/test_tenant_service.py`:

```python
async def test_list_staff_reads_the_named_tenant_not_the_ambient_one(super_admin, db)
async def test_list_staff_requires_super_admin(db)
async def test_list_staff_is_empty_for_a_fresh_tenant(super_admin, db)
```

The first is the one that matters: create staff in tenant A, call
`list_staff(actor, b.id)`, assert empty. Written naively against the ambient
tenant it returns A's staff and the test fails — which is the point.

---

## T1.2 — The derived checklist

**Depends on:** nothing (T1.1 and T1.2 can proceed in parallel).

### Where it lives

`application/services/tenant_setup_service.py`, exported from
`application/services/__init__.py` (`check_layer_exports.py` enforces the
export).

A service, not a repository helper: it composes several repositories and answers
a product question ("is this community usable yet"), which is exactly the
service layer's job. It performs **no writes**, so it takes no `actor` and
writes no audit row.

### The type and the query

```python
@dataclass(frozen=True)
class SetupStep:
    key: str
    label: str
    done: bool
    #: Why this matters, shown under the label when not done.
    hint: str
    #: Admin tab this step is completed on, for the "Take me there" link.
    tab: str
    #: A community cannot schedule a match until every required step is done.
    required: bool
```

Five steps, in the order the audit found missing (RC1 — *"nothing tells a new
admin that tournament → stage → enrolment → match is the order"*):

| key | required | Done when | Tab |
|---|:---:|---|---|
| `staff` | yes | any `UserRole` with `Role.STAFF` in this tenant | Users |
| `tournament` | yes | any `Tournament` in this tenant | Tournaments |
| `enrolment` | yes | any `TournamentPlayers` row in this tenant | Tournaments |
| `stream_room` | no | any `StreamRoom` in this tenant | Stream Rooms |
| `event_window` | no | the tenant's `SystemConfiguration` sets one | Settings |

The last two are **advisory on purpose.** Settings' own copy says *"Leave blank
to derive the event window from scheduled match times"*, and a match schedules
without a stream room — so marking either required would be the UI contradicting
the service, which is the mistake the whole reviews directory is about. Show
them, do not block on them.

```python
class TenantSetupService:
    """Whether a community has what it needs to run, derived on every read.

    Nothing here is stored: a tenant that deletes its last tournament becomes
    un-set-up again, and the checklist says so. See the tenant-onboarding plan,
    design decision 3.
    """

    async def status(self) -> list[SetupStep]:
        """The checklist for the tenant in scope."""

    @staticmethod
    async def status_for(tenant_id: int) -> list[SetupStep]:
        """The checklist for a named tenant — the /platform caller (T1.5)."""

    @staticmethod
    def is_ready(steps: list[SetupStep]) -> bool:
        return all(s.done for s in steps if s.required)
```

`status()` reads the ambient tenant via the normal `scoped(...)` repositories.
`status_for(tenant_id)` wraps `tenant_scope(tenant_id)` and delegates — one
derivation, two entry points, the same shape as T1.1's `list_staff`.

### Cost

Five `.exists()` calls, on a page that already issues far more. Do not
pre-optimise into a single joined query — five named existence checks are what
makes the next step readable when a sixth is added. If it ever matters, the
place to cache is the request, not the row.

### Tests

`tests/services/test_tenant_setup_service.py` (new file):

```python
async def test_a_fresh_tenant_has_no_completed_steps(db)
async def test_granting_staff_completes_the_staff_step(db)
async def test_enrolment_step_needs_a_player_not_just_a_tournament(db)
async def test_is_ready_ignores_the_advisory_steps(db)
async def test_deleting_the_last_tournament_makes_the_tenant_unready_again(db)
async def test_status_for_reads_the_named_tenant_not_the_ambient_one(db)
```

The last two carry the design decisions: derived-not-stored, and explicit
scoping. Also add a leak test in `tests/tenancy/` asserting tenant A's rows never
complete tenant B's steps — this service touches five scoped models and is
exactly the shape `test_leak_test_coverage.py` exists to catch.

---

## T1.3 — Land the new admin on the checklist

**Depends on:** T1.2.

### Files

- `pages/admin.py` (the tab list and which one is selected)
- `theme/` — a new `setup_checklist.py` panel

### The change

`pages/admin.py` builds `tabs` and sorts by `_ADMIN_GROUP_ORDER`
([lines 122-174](../../../pages/admin.py#L122)), so Schedule is first and
`/admin` opens on it. Two edits:

1. Build the checklist once (`TenantSetupService().status()`, beside the
   `enabled_flags()` load at [line 89](../../../pages/admin.py#L89) — both are
   one-per-page-load reads feeding tab construction).
2. **When the tenant is not ready**, prepend a `Setup` tab in group
   `Operations` and make it the default section. When it is ready, do not add
   the tab at all.

A tab, not a modal or a banner: it is addressable, it is dismissible by simply
clicking another tab, and it vanishes on its own. The alternative — a persistent
banner across every tab — is the thing every admin learns to ignore.

**Do not hide the other tabs.** The audit's complaint about the 19-item drawer
(RC1) is that nothing *sequences* the setup, not that the drawer is wrong;
hiding tabs from a staff member who knows what they want is a worse failure than
showing too many. The checklist supplies the order; the drawer stays.

### The panel

Per step: state icon (`check_circle` positive / `radio_button_unchecked` grey),
label, hint when not done, and a button switching to the step's tab. Required
steps first, advisory ones under a *"Recommended, not required"* subheading —
carrying the required/advisory distinction to the screen, or T1.2's care about
it was wasted.

Head it with what the audit says nothing says today: *"tournament → enrol
players → schedule a match"*.

### NiceGUI

The tab-switch buttons run in the page's slot context; if any handler is
scheduled with `background_tasks.create`, capture `context.client` first and
restore it with `with client:` — `enforce_nicegui_client_api.py` and
`check_slot_context.py` both watch this. Use `@ui.refreshable` for the panel so
completing a step can re-derive without a page rebuild.

### Tests

`tests/test_admin_setup_checklist.py` — the tab-construction logic is plain
Python and testable without a browser:

```python
async def test_setup_tab_is_present_and_default_for_an_unready_tenant(db)
async def test_setup_tab_is_absent_once_required_steps_are_done(db)
async def test_schedule_is_still_the_default_for_a_ready_tenant(db)
```

Follow whatever `pages/admin.py` is already tested by; if the tab list is not
currently reachable from a test, extract the construction into a module-level
helper that takes `(steps, flags, roles)` and returns the list, and test that.

---

## T1.4 — Make the empty tournament select say so

**Depends on:** nothing.

### Files

- `theme/dialog/match_dialog.py` — `_render_tournament_select`
  ([lines 80-86](../../../theme/dialog/match_dialog.py#L80))

### The change

Measured: with no tournaments the select *"opens no menu at all (0 options)"*
and Create answers *"Please fill required field(s): Tournament."* One helper
backs both the admin dialog ([line 420](../../../theme/dialog/match_dialog.py#L420))
and the player-request dialog ([line 687](../../../theme/dialog/match_dialog.py#L687)),
so one change fixes both surfaces.

When `tournaments` is empty, disable the select and give it a hint that names
the missing thing and where to make it:

```python
    def _render_tournament_select(self, tournaments, default_value):
        select = ui.select(
            label='Tournament *',
            options={t.id: t.name for t in tournaments},
            value=default_value,
            with_input=True,
        ).props('required').classes('input-full-width')
        if not tournaments:
            select.disable()
            select.props('hint="No tournaments yet — create one on the Tournaments tab."')
        return select
```

The two dialogs need different wording — a player requesting a match cannot
visit the Tournaments tab. Pass the sentence in rather than branching on
tournament-ness inside the helper; the player dialog's is closer to *"No
tournaments are open for requests right now."*

This is the local fix for F1. The sequencing problem behind it is T1.3's; both
ship in this wave because the hint alone is a consolation prize and the
checklist alone leaves a dead control on the busiest page.

### Tests

Extend whatever covers `match_dialog` today. If the helper is not currently
reachable from a test, this is the argument for making it a module-level
function taking `(tournaments, empty_hint)` — then:

```python
def test_tournament_select_is_disabled_and_hinted_when_there_are_none()
def test_tournament_select_is_enabled_when_there_are_some()
```

---

## T1.5 — A readiness column on `/platform`

**Depends on:** T1.2.

### Files

- `pages/platform.py` — `_refresh` ([lines 317-329](../../../pages/platform.py#L317)),
  the `columns` list ([92-100](../../../pages/platform.py#L92)), and the `item`
  grid slot ([112-139](../../../pages/platform.py#L112))

### The change

F7: the row shows name, slug, domain, guild, active, Edit, Features — *"a
super-admin who provisions ten communities cannot tell which of them have a
staff member, a tournament or a stage."* Add a **Setup** column fed by
`TenantSetupService.status_for(t.id)`: `Ready` when
`is_ready`, otherwise the count of outstanding required steps (`2 of 3`) with a
tooltip naming them.

`_refresh` currently builds rows from `list_tenants()` alone. Awaiting five
existence checks per tenant is now N×5 queries; at `/platform` scale (tens of
tenants, super-admin only, not a hot path) that is acceptable and simpler than a
bespoke aggregate. **Say so in a comment** so the next reader does not mistake it
for an oversight — and if the tenant list ever grows past a few hundred, the fix
is one grouped query in `TenantSetupService`, not scattered caching.

Mirror the column into the `item` slot — `check_table_grid.py` enforces the
mobile grid, and this table already has a bespoke `item` slot to extend.

### Tests

```python
async def test_platform_rows_report_readiness(db)          # ready and not-ready
async def test_readiness_counts_only_required_steps(db)
```

---

## T1.6 — The two bare zero states

**Depends on:** nothing.

### Files

- `pages/admin_tabs/admin_settings.py` — the Stream Rooms table
- `pages/admin_tabs/admin_feedback.py` — the Feedback table

### The change

Both show Quasar's default `No data available`;
[`theme/empty_state.py`](../../../theme/empty_state.py) has `no_data_slot(message, icon)`
and the codebase uses it well elsewhere. Add the slot to each table.

The audit names the model to copy — Discord Roles, which says *what is missing,
what connecting requires, and the button that does it*. Match that shape:

- Stream Rooms → `no_data_slot('No stream rooms yet — add one for each stage or capture station you run matches on.', icon='tv')`
- Feedback → `no_data_slot('No feedback submitted yet.', icon='feedback')`

Feedback's empty state is genuinely terminal (staff cannot manufacture
feedback), so it gets no call to action; Stream Rooms' explains the concept,
because on day one nobody knows what a stream room is for. `no_data_slot`
HTML-escapes its message, so no markup in these strings.

### Tests

`check_markdown_xss.py` and the escaping are already covered. A render test is
disproportionate here — verify by screenshot on the fresh tenant, and note in
the commit that this is the F6 fix.

---

## T1.7 — A half-provisioned tenant in the dev seed

**Depends on:** T1.2.

### Files

- `scripts/seed_dev.py`

### Why

Every seeded tenant is fully populated and a `TenantMembership` is created for
each user ([line 188](../../../scripts/seed_dev.py#L188)) — so the checklist is
complete everywhere and **the panel this wave builds is invisible in the dev
environment.** CLAUDE.md's step 6: *"a feature the seed never creates is a
feature no one can see in the running app."*

### The change

Add a third tenant — slug `fledgling`, name something like "Fledgling
Community" — deliberately stopped part-way: a STAFF grant and a membership for
one seeded user, **no tournament, no enrolment, no stream room.** That is
`staff` done, `tournament`/`enrolment`/`stream_room` outstanding, which exercises
the panel's mixed state, T1.5's `2 of 3`, and T1.4's disabled select in one
login.

Keep it idempotent (`get_or_create`) and tenant-scoped like the existing rows.
Do **not** make it a full tenant "and then delete things" — the seed is read as
documentation of what a state looks like.

The existing tenants stay fully provisioned: a reviewer needs both the ready and
the unready case, and the ready one is what proves the panel disappears.

### Tests

`tests/test_seed_coverage.py` may assert per-model coverage; check whether a new
tenant needs registering there. Add:

```python
async def test_the_fledgling_tenant_is_not_setup_complete(db)
```

---

## T1.8 — Docs

- [`docs/features/multitenancy.md`](../../features/multitenancy.md) — a short
  section on provisioning: creating a tenant writes one row, the first admin is
  granted from `/platform` (or `scripts/seed_tenant.py --operator-discord-id`),
  and readiness is derived by `TenantSetupService`, never stored.
- [`docs/reference/services.md`](../../reference/services.md) — a row for
  `TenantSetupService`, and note `TenantService.list_staff`.
- [`docs/development.md`](../../development.md) — the `fledgling` tenant and
  what it is for, wherever the seeded fixtures are described.
- [`docs/reviews/new-tenant-onboarding-ux.md`](../../reviews/new-tenant-onboarding-ux.md)
  — **do not edit or delete it.** It is deleted with this directory when wave 4
  lands. An audit rewritten as its findings ship stops being a record of what
  was measured.

## Wave 1 wrap-up

```bash
poetry run pytest
grep -rn "bootstrap_staff" --include=*.py pages/
```

That grep must now return a hit — the finding this wave opened with was that it
returned none.

Then, on a **freshly created** tenant (README's verification loop, not the
seeded `default`):

- `/platform` shows the new tenant as not ready, and the Admins dialog grants
  its first staff member.
- As that staff member, `/t/<slug>/admin` opens on **Setup**, not Schedule.
- The Schedule tab's Create Match still exists and its Tournament select is
  disabled with a hint rather than silently empty.
- Complete the three required steps; the Setup tab disappears and `/admin`
  falls back to Schedule.
- Re-check at 390×844 — the checklist panel and the new `/platform` column both
  have grid slots to verify.

Commit as *"Give a new community a first admin and an order to set it up in"*.
