# Wave 2 — membership becomes the answer to "who is in this community"

**Read [README.md](README.md) first.**

No migration and **no authorization change** — nothing is gated on membership
until wave 4. What changes is that `TenantMembership` stops being a write-only
table: it acquires an invariant, a service, a management surface, and seven
callers.

Fixes audit finding **F2** (the Users tab lists every user on the platform), the
picker half of **F3**, and the platform-leak
[cross-cutting theme](../../reviews/README.md#cross-cutting-themes). After this
wave both Critical findings are closed and **you can stop here**.

| Task | Touches | Size |
|---|---|---|
| T2.1 | The invariant: a role in a tenant implies membership | medium |
| T2.2 | `TenantMembershipService` — add, remove, list, with audit + events | medium |
| T2.3 | The member-scoped user query | small |
| T2.4 | The five UI pickers | medium |
| T2.5 | The two entry surfaces (`api/`, `mcpserver/`) | small |
| T2.6 | The Users tab becomes member management | medium |
| T2.7 | Leak tests | small |
| T2.8 | Seed + docs | small |

**Do T2.1 first and do not reorder it.** Every task after it assumes membership
is a superset of "has a role here"; done in the other order, T2.4 hides the
community's own staff from its own pickers.

---

## T2.1 — A role in a tenant implies membership in it

### The bug this wave would otherwise ship

Membership is currently a **frozen backfill**. The multitenancy migration
(`20_20260712000000_multitenancy.py`) wrote a `TenantMembership` per existing
user and nothing has written one since, except
`TenantService.bootstrap_staff` — which pairs the two deliberately
([`tenant_service.py:290-292`](../../../application/services/tenant_service.py#L290)).
Grepped on this branch, **every other role-grant path writes a role and no
membership**:

| Path | Writes `UserRole` | Writes `TenantMembership` |
|---|:---:|:---:|
| `TenantService.bootstrap_staff` | yes | **yes** |
| [`UserService.grant_role`](../../../application/services/user_service.py#L322) — the Users tab's grant | yes | no |
| `DiscordRoleMappingService` — guild-role → app-role sync | yes | no |
| [`UserService.provision_from_discord_login`](../../../application/services/user_service.py#L73) — first login | n/a | no |

So a user created after the migration has **no membership anywhere**, and a
staff member granted through the Users tab is not a member of the community they
administer. Scope the pickers on that (T2.4) and a community's own staff vanish
from its own Commentators select. Close the gate on it (wave 4) and they are
locked out of the community they run.

### The invariant

> **Holding any role in a tenant implies membership in that tenant.**

Membership is the wider set: a member may hold no roles (a player), but nobody
holds a role without being a member. Enforce it where roles are written, not by
a periodic reconciler.

### Files

- `application/services/user_service.py` — `grant_role`
- `application/services/discord/discord_role_mapping_service.py` — the sync
  write
- `application/services/tenant_service.py` — `bootstrap_staff` already complies;
  leave it, but point its comment at the invariant

### The change

In `grant_role`, add the membership beside the role, and pair audit + event
through `write_and_publish` (T2.2 defines the event):

```python
    async def grant_role(self, target: User, role: Role, actor: User) -> None:
        await AuthService.ensure(
            await AuthService.can_grant_roles(actor),
            "Only Staff can grant roles",
        )
        await self.role_repository.add(target, role, granted_by=actor, source=RoleSource.MANUAL)
        # A role in a tenant implies membership in it — see the tenant-onboarding
        # plan, wave 2. Idempotent: the repository get_or_creates.
        await TenantMembershipService().ensure_member(target)
        ...
```

`SUPER_ADMIN` is the exception and must stay one: its `UserRole` carries
`tenant=NULL` and it belongs to no community. Guard explicitly —
`if role is not Role.SUPER_ADMIN` — rather than relying on the ambient tenant
being absent, because `grant_role` runs *inside* a tenant context and would
otherwise make every super-admin a member of whichever community granted them.

The Discord sync path is **fail-open by design** (its docstring at
[line 164](../../../application/services/discord/discord_role_mapping_service.py#L164)
says *"Never raises"*). Preserve that: a membership write that fails must not
break role sync. Add it inside the existing error handling, not around it.

**Do not** add membership on login. Wave 4 needs "logged in" and "belongs here"
to be different states, and an auto-join on first visit collapses them.

### Backfill

Roles granted between the migration and this wave have no membership. Add a
one-shot reconciliation to the migration for this change — or, if these waves
ship without a schema migration as planned, a script
(`scripts/backfill_memberships.py`) that inserts a membership for every
`(user, tenant)` in `userrole` where `tenant IS NOT NULL` and no membership
exists. Idempotent, safe to re-run, and **wave 4's first task re-runs it and
audits the result before closing the gate.**

### Tests

`tests/services/test_user_service.py`:

```python
async def test_granting_a_role_makes_the_user_a_member(db)
async def test_granting_a_role_twice_makes_one_membership(db)
async def test_granting_super_admin_makes_no_membership(db)
async def test_revoking_a_role_leaves_membership_intact(db)
```

The third and fourth carry the design: super-admin is global, and membership is
the wider set — losing a role does not eject you from the community.

Add an invariant test in `tests/tenancy/`:

```python
async def test_no_tenant_scoped_role_exists_without_a_membership(db)
```

Grant roles by every service path the suite can reach, then assert the join is
empty. That is the test that catches the *next* role-granting path somebody adds.

---

## T2.2 — `TenantMembershipService`

**Depends on:** nothing (T2.1 consumes it; write this first if working strictly
in order).

### Where it lives

`application/services/tenant_membership_service.py`, exported from
`application/services/__init__.py`.

Membership operations currently exist only as
[`TenantMembershipRepository`](../../../application/repositories/tenant_membership_repository.py)
plus a passthrough `TenantService.is_member`. They need a service because they
now carry rules (the T2.1 invariant), authorization (only staff manage members),
audit rows and events — none of which belong in a repository.

`TenantService` keeps `is_member` as a passthrough; it is called from tenancy
machinery and moving it would churn callers for nothing.

### The surface

```python
class TenantMembershipService:
    """Who belongs to a community, and who may change that.

    Membership is the wider set: every role-holder is a member, not every member
    holds a role. ``TenantMembership`` is exempt from ``check_tenant_scoping``
    (cross-tenant by nature) — its queries pass tenant ids explicitly.
    """

    async def list_members(self) -> list[User]: ...
    async def add_member(self, actor: User, user: User) -> None: ...
    async def remove_member(self, actor: User, user: User) -> None: ...
    async def ensure_member(self, user: User) -> None:
        """Idempotent, unaudited membership for the in-scope tenant.

        The T2.1 invariant's hook: called from a role grant that is audited in
        its own right, so a second audit row would only be noise.
        """
```

`add_member` / `remove_member` authorize on `AuthService.can_grant_roles(actor)`
— the same gate the Users tab's role grants already use, so member management
and role management need identical authority. Both raise `ValueError` for
user-facing failures.

**`remove_member` must refuse to eject a role-holder** — that would break T2.1's
invariant from the other side:

```python
        held = await AuthService.get_roles(user)
        if held:
            raise ValueError(
                f"{user.display_name or user.username} holds roles in this "
                "community — revoke them before removing the membership."
            )
```

Refuse rather than cascade-revoke: silently stripping someone's roles because
staff clicked Remove on a table row is exactly the kind of invisible side effect
the reviews keep finding.

### Audit + events

`AuditActions` (`application/services/audit_service.py`, beside
`TENANT_CREATED` at [line 314](../../../application/services/audit_service.py#L314)):

```python
    TENANT_MEMBER_ADDED = 'tenant.member_added'
    TENANT_MEMBER_REMOVED = 'tenant.member_removed'
```

`EventType` (`application/events/event_types.py`) has **no tenancy members
today** — add both, mirroring the action names, and add them to `EventType.ALL`.
`check_event_types.py` enforces the pair, `check_audit_actions.py` the constant.
`EventType` is an external contract: add, never rename.

Use `write_and_publish` for both operations —
`check_dry_regressions.py` blocks a hand-rolled `write_log` +
`event_bus.publish` sequence:

```python
        await self.audit_service.write_and_publish(
            actor, AuditActions.TENANT_MEMBER_ADDED,
            {'target_user_id': user.id},
            EventType.TENANT_MEMBER_ADDED,
        )
```

Pass `actor` explicitly and never guard with `if actor:`.

### Tests

`tests/services/test_tenant_membership_service.py`:

```python
async def test_add_member_requires_role_granting_authority(db)
async def test_add_member_is_idempotent(db)
async def test_remove_member_refuses_while_roles_are_held(db)
async def test_remove_member_succeeds_once_roles_are_revoked(db)
async def test_list_members_returns_only_this_tenants_members(db)
async def test_membership_changes_are_audited_and_published(db)
```

---

## T2.3 — The member-scoped user query

**Depends on:** T2.2.

### Files

- `application/repositories/user_repository.py`
- `application/services/user_service.py`

### The change

Design decision 7: **do not change `UserRepository.get_all`.** It is
`User.all().order_by('username')` with optional role/discord filters
([lines 46-65](../../../application/repositories/user_repository.py#L46)) and it
has a legitimate platform-level caller (wave 1's first-admin picker). Add a
sibling:

```python
    @staticmethod
    async def get_members(
        role: Optional[Role] = None,
        has_discord: bool = False,
    ) -> List[User]:
        """Users who belong to the tenant in scope.

        Joins through ``TenantMembership``. ``User`` is global — this is the only
        correct way to ask "who is in this community", and it is what every
        per-community picker wants. ``get_all`` remains for platform-level
        callers.
        """
        query = User.filter(
            tenant_memberships__tenant_id=require_tenant_id(),
        ).order_by('username')
        ...
```

The reverse relation is `tenant_memberships`
([`models/user.py:87`](../../../models/user.py#L87)). Keep the `role` and
`has_discord` filters identical to `get_all`'s so converting a caller is a
one-word change. Add `.distinct()` if the role filter joins produce duplicates —
`get_all` already does this for the role case.

`require_tenant_id()` **raising** with no tenant in scope is correct and wanted:
a per-community picker rendered outside a tenant is a bug, and this is where it
should surface loudly.

Expose it as `UserService.get_community_users(...)` with the same signature as
`get_all_users`.

### Tests

`tests/services/test_user_service.py` and a leak test in T2.7:

```python
async def test_get_community_users_excludes_non_members(db)
async def test_get_community_users_honours_the_role_filter(db)
async def test_get_community_users_raises_without_a_tenant(db)
async def test_get_all_users_is_unchanged(db)     # the regression guard
```

---

## T2.4 — Convert the five UI pickers

**Depends on:** T2.1 (or the community's own staff disappear), T2.3.

### The call sites

Every one becomes `get_community_users()`:

| File | Line | Picker |
|---|---:|---|
| [`theme/dialog/match_dialog.py`](../../../theme/dialog/match_dialog.py#L374) | 374 | Commentators, Trackers, and Players under "Choose any players" |
| [`theme/dialog/match_dialog.py`](../../../theme/dialog/match_dialog.py#L640) | 640 | The player-request dialog's equivalents |
| [`theme/dialog/checkout_dialog.py`](../../../theme/dialog/checkout_dialog.py#L28) | 28 | The equipment borrower |
| [`theme/dialog/equipment_dialog.py`](../../../theme/dialog/equipment_dialog.py#L33) | 33 | The equipment owner/assignee |
| [`pages/admin_tabs/admin_brackets/manage.py`](../../../pages/admin_tabs/admin_brackets/manage.py#L37) | 37 | Bracket entrants |

Mechanical — one method name each. Two things to check while there:

**`System` still appears.** The audit measured the `System` service account
offered as a player and used as one. Membership scoping removes it only if
`System` has no `TenantMembership`; the migration backfilled *every* user, so it
probably does. Check, and if so exclude service accounts at the repository level
in T2.3 rather than filtering in five places. If `User` has no flag
distinguishing a service account, **say so and leave `System` in scope** — do
not invent a column in this wave; note it for the plan's wrap-up.

**"Choose any players" now means "any member".** The checkbox label at
[`match_dialog.py:451`](../../../theme/dialog/match_dialog.py#L451) becomes
misleading the moment the list is scoped. Relabel it *"Include players not
enrolled in this tournament"* — which is what it has always actually done. Its
silent enrolment side effect stays in scope for wave 3.

### Tests

Where each dialog has a test, assert a non-member is absent from the options.
Where a dialog has none, the browser check in the wrap-up is the coverage — say
so in the commit rather than skipping it silently.

---

## T2.5 — The two entry surfaces

**Depends on:** T2.3.

### Files

- [`api/routers/users.py:56`](../../../api/routers/users.py#L56) — `GET /users`
- [`mcpserver/tools/people.py:56`](../../../mcpserver/tools/people.py#L56) — `list_users`

### Why this is its own task

The audit could not see these from a browser. Both run inside a tenant-scoped
context — an API token belongs to a tenant, an MCP session resolves one — and
both currently return **every user on the platform**. That is a larger leak than
the Users tab, because it is machine-readable and paginated by a client that
believes it is reading one community.

Both are entry surfaces: `enforce_architecture.py` classifies `api/` and
`mcpserver/` as presentation, so they call `UserService.get_community_users`,
never the repository.

### The compatibility question

`GET /users` changing what it returns is a **breaking change for API
consumers**, even though the new answer is the correct one. Do not add a
`?scope=all` escape hatch — that re-opens the leak with a query parameter. Ship
the narrowing, and note it in
[`docs/reference/rest-api.md`](../../reference/rest-api.md) as a behaviour
change with the reason. Call it out in the commit message.

The MCP tool has no such contract concern — it is read-only and its own server
instructions already frame every tool as community-scoped.

### Tests

`tests/api/` and `tests/mcp/` both have isolation suites
(`test_api_tenant_isolation.py`, `test_mcp_tenant_isolation.py`) — this belongs
in them:

```python
async def test_users_endpoint_returns_only_this_tenants_members(db)
async def test_mcp_list_users_returns_only_this_tenants_members(db)
```

---

## T2.6 — The Users tab becomes member management

**Depends on:** T2.2, T2.3.

### Files

- [`pages/admin_tabs/admin_users.py`](../../../pages/admin_tabs/admin_users.py)

### The change

F2, measured: 11 rows in a community 30 seconds old, under the caption
*"Everyone in this community and the roles they hold."* `get_query` returns
`User.all()` ([line 40](../../../pages/admin_tabs/admin_users.py#L37)). The
caption was already the truth; the query was not. Make the query match:

```python
        def get_query():
            sel_list = selected.get('value') or []
            qs = User.filter(tenant_memberships__tenant_id=require_tenant_id())
            ...
```

This is a read-only display query in presentation, which CLAUDE.md permits — but
it now hand-scopes, so it must use `require_tenant_id()` and not
`get_current_tenant_id()`. Prefer routing it through
`UserService.get_community_users` if the `UserTableView`'s `get_query` contract
allows a coroutine; if it requires a queryset, hand-scope and leave a comment
naming the service as the canonical version.

### Add Member

The tab's `Add User` button opens `AdminUserDialog`, which creates a *global*
user. With scoping, a staff member's more common need is *"this person exists,
put them in my community"* — and without it, the only way into a scoped picker
is to be granted a role, which is not what a player should need.

Add **Add Member**: a dialog with a user select over the global list (the
audit's own note that the edit dialog writes global profile fields applies —
this one writes only membership) calling
`TenantMembershipService.add_member`. Keep `Add User` for genuinely new accounts.

Add a **Remove** row action calling `remove_member`, which refuses while roles
are held (T2.2) and surfaces that refusal via `ui.notify(str(e), color='warning')`.

### Mobile

`UserTableView` is one of the four family tables with a bespoke `item` slot —
the new row action needs mirroring there. `check_table_grid.py` enforces it.

### Empty state

A community with one member (its first admin) should not read as broken. The
zero-ish state wants the wave 1 treatment: what a member is, and the button that
adds one.

### Tests

```python
async def test_users_tab_query_excludes_non_members(db)
async def test_role_filter_still_works_within_members(db)
```

---

## T2.7 — Leak tests

**Depends on:** T2.3–T2.6.

`tests/tenancy/` is the suite that makes this wave safe to trust.
`test_leak_test_coverage.py` records `TenantMembership` as *"cross-tenant by
nature; reads are always membership checks"* — that exemption is about the
membership table itself, and does **not** cover the new `User`-through-membership
joins. Add:

```python
async def test_community_user_list_never_crosses_tenants(db)
async def test_every_converted_picker_is_member_scoped(db)
```

The second is worth writing as a **grep-style guard** rather than six near-copies:
assert that no file under `theme/dialog/` or `pages/admin_tabs/` calls
`get_all_users(`, with an explicit allowlist for wave 1's platform picker. That
is what stops the seventh picker from being written against the global list — the
same shape as `check_seed_coverage.py`'s enforcement, and cheaper than a test per
dialog.

---

## T2.8 — Seed and docs

### Seed

`scripts/seed_dev.py` already creates a membership per seeded user
([line 188](../../../scripts/seed_dev.py#L188)), so the existing tenants keep
working. What it cannot currently produce is the case this wave is about: **a
platform user who is a member of one community and not another.** Add one —
a user seeded into `default` only, so a reviewer opening the second tenant's
pickers can see them absent.

Wave 1's `fledgling` tenant is the natural place: give it its staff member and
nobody else.

### Docs

- [`docs/features/multitenancy.md`](../../features/multitenancy.md) — replace
  the *"Authorization is tenant-scoped, not membership-gated"* section's
  implication that membership is inert. State the T2.1 invariant, that
  per-community person lists join through `TenantMembership`, and that the
  **gate** is still not in place (wave 4 changes that sentence again).
- [`docs/reference/services.md`](../../reference/services.md) —
  `TenantMembershipService`, and `UserService.get_community_users` beside
  `get_all_users` with a note on which to use.
- [`docs/reference/rest-api.md`](../../reference/rest-api.md) — the `GET /users`
  narrowing.
- [`docs/features/audit-logging.md`](../../features/audit-logging.md) and
  [`docs/features/event-system.md`](../../features/event-system.md) — the two
  new actions and event types.

## Wave 2 wrap-up

```bash
poetry run pytest
poetry run pytest tests/tenancy/
grep -rn "get_all_users(" --include=*.py pages/ theme/ api/ mcpserver/
```

That grep should return **exactly one** hit — wave 1's first-admin picker on
`/platform`. Seven before this wave; anything else is a converted call site
missed.

Then, on a freshly created tenant:

- Its Users tab lists **its** members, not the platform's.
- Add Member adds someone; Remove refuses while they hold a role and succeeds
  after the role is revoked.
- Create Match's Commentators/Trackers/Players offer only members — and the
  community's own staff **are** among them (the T2.1 check).
- A user with no membership in this tenant can still reach its pages. That is
  correct until wave 4; confirm it deliberately rather than assuming.
- 390×844 for the Users table's grid card and its new Remove action.

Commit as *"Make community membership real, and scope every person picker to it"*.
