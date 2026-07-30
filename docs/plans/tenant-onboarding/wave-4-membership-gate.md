# Wave 4 — the gate, and the door beside it

**Read [README.md](README.md) first.**

The only wave that changes authorization, and the only one with a migration.
Afterwards, a community is visible to the people who belong to it, and everyone
else gets a way in rather than a wall.

Fixes audit finding **F5** and root cause **RC4**.

| Task | Touches | Size |
|---|---|---|
| T4.1 | The backfill audit — **who would this lock out?** | medium |
| T4.2 | `TenantJoinRequest` + migration | medium |
| T4.3 | The door: request access, and the staff queue | large |
| T4.4 | The gate in `_tenant_page` | medium |
| T4.5 | What stays public | small |
| T4.6 | Non-request paths: bot, workers, API, MCP | medium |
| T4.7 | Access tests | medium |
| T4.8 | Seed + docs | small |

**T4.1 runs first and its result is a go/no-go.** The gate does not close until
the backfill is proven complete on real data. If T4.1 finds users this would
lock out and cannot account for them, **stop and report** — do not close the
gate and let support absorb it.

---

## T4.1 — Who would this lock out?

### The risk

`middleware/auth.py:162-168` is honest about why no gate exists today: *"there
is no separate 'must be a member' gate, since the app has no self-serve/invite
enrollment path and it would lock out new users."* Wave 4 removes both halves of
that sentence — but only if membership genuinely covers everyone who is using
the app right now.

What is known about the coverage:

- The multitenancy migration (`20_20260712000000_multitenancy.py`) backfilled a
  `TenantMembership` **per existing user** at that point.
- Nothing wrote one afterwards except `TenantService.bootstrap_staff` — until
  wave 2's invariant and its `scripts/backfill_memberships.py`.
- So the exposure is **users created after the multitenancy migration who never
  received a role**: ordinary players and crew. Wave 2's backfill covers
  role-holders only, and by design.

### The task

Write `scripts/audit_membership_coverage.py` — read-only, safe to run against
production — that reports, per tenant, users with **evidence of participation
but no membership**. Evidence, in rough order of strength:

| Signal | Model |
|---|---|
| Enrolled in one of its tournaments | `TournamentPlayers` |
| Played in one of its matches | `MatchPlayers` |
| Signed up or was approved as crew | the match-crew model |
| Took a volunteer shift | the volunteer models |
| Holds a role there | `UserRole` (wave 2 should have covered these — report any remainder as a wave-2 bug) |
| Appears as an actor in its audit log | `AuditLog` |

Output a per-tenant count and a sample, not just a total: one tenant with 300
uncovered users is a different decision from thirty tenants with ten each.

Then extend `scripts/backfill_memberships.py` to grant membership on the first
five signals. **Not the audit-log signal** — appearing in an audit row can mean
someone acted *on* you, not that you belong; use it for the report only, and
hand-review whatever it surfaces that the others do not.

### The go/no-go

Run the audit, run the backfill, run the audit again. The second run must report
zero on the first five signals. Record both outputs in the commit message —
this is the evidence that the gate is safe to close, and it belongs in git
history rather than in someone's terminal scrollback.

Users with **no** participation signal in any tenant are the genuinely correct
"not a member of anything" case: after this wave they meet T4.3's door. Say how
many there are so nobody is surprised by the support volume.

### Tests

```python
async def test_audit_reports_a_participant_without_a_membership(db)
async def test_backfill_grants_membership_for_each_covered_signal(db)
async def test_backfill_is_idempotent(db)
async def test_backfill_ignores_the_audit_log_signal(db)
```

---

## T4.2 — `TenantJoinRequest`

**Depends on:** T4.1 (do not build the door until the backfill is proven).

### The model

`models/tenant.py`, beside `TenantMembership`, exported from
`models/__init__.py`:

```python
class TenantJoinRequest(Model):
    """Someone asking to join a community they can see the door of.

    The enrollment path whose absence is the documented reason no membership
    gate exists (``middleware/auth.py``). Cross-tenant by nature, like
    ``TenantMembership``: a user's own list of pending requests spans tenants.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='join_requests', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='join_requests', on_delete=fields.CASCADE)
    status = fields.CharEnumField(JoinRequestStatus, default=JoinRequestStatus.PENDING, max_length=20)
    message = fields.CharField(max_length=500, null=True)
    decided_by = fields.ForeignKeyField('models.User', related_name='join_requests_decided', null=True, on_delete=fields.SET_NULL)
    decided_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'tenantjoinrequest'
        unique_together = (('user', 'tenant'),)
        indexes = (('tenant', 'status'),)   # the staff queue's query
```

`JoinRequestStatus` in `models/enums.py`: `PENDING`, `APPROVED`, `DENIED`.

Decisions baked in, and worth defending if questioned:

- **`unique_together` on `(user, tenant)`**, not one row per attempt. A denied
  request is re-openable by updating the row; an append-only log of attempts is
  a spam vector with no reader.
- **`decided_by` is `SET_NULL`**, matching `Tenant.feature_group`'s reasoning —
  deleting a staff account must not delete the record of the decision.
- **`message` is bounded at 500** and rendered as text, never markup.
  `check_markdown_xss.py` watches this; the column guard turns an over-long
  value into a `ValueError` rather than a 500.
- **Add it to `check_tenant_scoping.py`'s `EXEMPT_MODELS`**, with the same
  justification as `TenantMembership`: tenant is the row's subject. Record the
  reason in `tests/tenancy/test_leak_test_coverage.py` alongside the existing
  entry — that file is where these exemptions are explained.

### Migration

```bash
poetry run aerich migrate && poetry run aerich upgrade
```

`enforce_migration_safety.py` and `check_migration_drift.py` both run on this.
One new table with no alterations to existing ones — the safest shape — but read
the generated file before committing rather than trusting the generator.

### Tests

`tests/tenancy/` gets the isolation test `check_seed_coverage.py` and
`test_leak_test_coverage.py` will both require for a new tenant-scoped model.

---

## T4.3 — The door

**Depends on:** T4.2.

### The service

`application/services/tenant_membership_service.py` (wave 2's), extended:

```python
    async def request_to_join(self, user: User, tenant_id: int, message: str | None) -> None:
    async def approve_request(self, actor: User, request_id: int) -> None:
    async def deny_request(self, actor: User, request_id: int) -> None:
    async def list_pending(self) -> list[TenantJoinRequest]:
```

`request_to_join` takes an explicit `tenant_id` — it is called from a page the
requester is **not yet a member of**, so it must not depend on anything
membership-scoped. It refuses when the user is already a member (`ValueError`,
not a silent no-op) and re-opens a `DENIED` row rather than creating a second.

`approve_request` **creates the membership** — it is the only new caller of
`add_member` that does not go through staff picking a name. Both decisions
authorize on `AuthService.can_grant_roles`, matching wave 2.

### Audit + events

New `AuditActions`, namespaced `verb.object` like the rest:

```python
    TENANT_JOIN_REQUESTED = 'tenant.join_requested'
    TENANT_JOIN_APPROVED = 'tenant.join_approved'
    TENANT_JOIN_DENIED = 'tenant.join_denied'
```

Matching `EventType` members, added to `EventType.ALL`. All three through
`write_and_publish`.

`request_to_join`'s actor is the **requester** — they are acting on their own
behalf, and `AuditService` takes `actor` explicitly and never guards with
`if actor:`. The audit row's tenant is the *target* tenant, which the requester
is not scoped to; wrap the write in `tenant_scope(tenant_id)` the way
`bootstrap_staff` does, or the row lands unscoped.

### The requester's surface

A non-member reaching a gated page gets this instead of a 403 (T4.4 routes them
here): the community's name, one sentence, an optional message box, and
**Request access**. Once pending, the same page says so and offers nothing else.

**Notify staff.** A request nobody sees is worse than no request. Wire the
`TENANT_JOIN_REQUESTED` event to the existing Discord notification path the way
other events are; the reviews' recurring finding is that
[notification is one-directional](../../reviews/README.md#cross-cutting-themes)
— so notify the requester on **both** approve and deny, not only approve.

### The staff surface

A **Members** section on the Users tab (wave 2 made it member management) or its
own tab if the tab is getting long — pending requests with Approve / Deny, and
the requester's message.

Do not make this a report. The reviews' *"discovery and action live on different
pages"* theme is precisely this mistake: the queue must carry its own buttons.

### Tests

```python
async def test_request_to_join_is_refused_for_an_existing_member(db)
async def test_a_denied_request_can_be_reopened_not_duplicated(db)
async def test_approving_creates_the_membership(db)
async def test_denying_creates_no_membership(db)
async def test_decisions_require_role_granting_authority(db)
async def test_the_requester_is_notified_on_approve_and_on_deny(db)
async def test_the_join_audit_row_is_stamped_with_the_target_tenant(db)
```

---

## T4.4 — The gate

**Depends on:** T4.1 (proven), T4.3 (the door exists).

### Files

- [`middleware/auth.py`](../../../middleware/auth.py) — `_tenant_page`, the
  shared implementation of `protected_page` and `public_page`
  ([lines 93-193](../../../middleware/auth.py#L93))

### The change

The membership check goes **after** the feature gate and **before** the role
gate, and applies only when `require_auth` is true — that is the line between
`protected_page` and `public_page`, and it is already the right line:

```python
            # Membership gate: a community is visible to the people who belong
            # to it. Only for auth-requiring routes — a @public_page (the
            # spectator bracket views) stays world-readable. SUPER_ADMIN
            # bypasses, exactly as it bypasses the role gate below.
            if require_auth:
                user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
                if not await AuthService.is_super_admin(user):
                    if user is None or not await TenantService.is_member(user.id, tid):
                        render_join_page(tenant_id=tid, user=user)
                        return
```

Four things that are easy to get wrong:

- **Render the door, not a 403.** `render_error_page(403, 'Forbidden')` is what
  the role gate does and is wrong here: not-a-member is a state with a remedy,
  and forbidden-by-role is not.
- **`SUPER_ADMIN` bypasses.** They belong to no community by design (wave 2's
  T2.1 guard) and must still reach every one.
- **The user is now loaded on every tenant page**, not only gated ones. That is
  one extra query per page load on a surface that already issues many, and it is
  unavoidable — but resolve it **once** and hand it to the role gate below,
  which currently loads it again. Net cost on a gated page is zero.
- **Do not gate on `is_active`.** An inactive tenant is a separate concern with
  its own handling; conflating them makes both harder to reason about.

Replace the `162-168` comment. It documents the absence of this gate and its
reason, and leaving it in place next to the gate is worse than no comment.

### Blast radius

Every tenant page shares this function. Before committing, enumerate the routes:
`protected_routes` is a module-level set — dump it and check each entry against
the intended posture. Anything surprising is a finding, not a rounding error.

---

## T4.5 — What stays public

**Depends on:** T4.4.

`public_page` routes are world-readable by design — currently the bracket views
(`tests/test_public_bracket_access.py` guards this). The `require_auth` condition
in T4.4 preserves that, but **prove it rather than assume it**:

```python
async def test_public_bracket_is_reachable_by_a_non_member(db)
async def test_public_bracket_is_reachable_signed_out(db)
```

Also check `/login`, `/logout`, the OAuth callbacks, the MCP consent page, and
the service-health view: any of them behind the new gate is a lockout that
cannot be recovered from inside the app. `_RESERVED_SLUGS` in `TenantService`
lists the platform-owned paths and is a good cross-check.

Add the pair to `tests/tenancy/test_tenant_urls.py` or the public-access suite,
whichever already owns route posture.

---

## T4.6 — The paths that are not page requests

**Depends on:** T4.4.

The gate lives in `_tenant_page`, so **nothing else is affected** — which is
both the good news and the thing to verify deliberately rather than assume.

| Surface | Posture | Why |
|---|---|---|
| REST (`api/`) | unchanged | A token belongs to a tenant; membership is a property of a *person* reaching a page. Wave 2 already scoped what it returns. |
| MCP (`mcpserver/`) | unchanged | Same — and `whoami` already reports which communities the caller belongs to. |
| Discord bot | unchanged | An interaction handler acts for a user who was assigned or signed up, i.e. already a member. |
| Workers / `background_tasks` | unchanged | They run in `tenant_scope`, not as a user. |

Two real gaps to close:

**Crew signup is the audit's actual symptom.** F5's measurement was not that a
stranger *saw* the schedule — it was that they were *offered Sign Up*. The page
gate stops them reaching the surface, but the reviews' standing rule is that
UI-only gating is not gating: **the crew-signup service must also refuse a
non-member.** Add the check there, with a `ValueError`, and a test.

**Deep links from Discord.** A DM links to a match page. If the recipient is not
a member, they now land on the door — check that the link survives the redirect
so approving them lands them where they were going, rather than at the community
root.

---

## T4.7 — Access tests

**Depends on:** T4.4, T4.5, T4.6.

This is the wave's safety net and deserves its own task rather than a line in
each of the others. In `tests/tenancy/`:

```python
async def test_a_non_member_cannot_reach_a_tenant_page(db)
async def test_a_non_member_sees_the_join_page_not_a_403(db)
async def test_a_member_reaches_it_normally(db)
async def test_a_super_admin_reaches_every_tenant_without_membership(db)
async def test_a_role_holder_is_a_member_and_reaches_it(db)      # wave 2's invariant, end to end
async def test_crew_signup_refuses_a_non_member_at_the_service(db)
async def test_membership_in_one_tenant_grants_nothing_in_another(db)
```

The last is the audit's exact scenario — `player_two` in `audit-third` — and is
the one to write first.

---

## T4.8 — Seed and docs

### Seed

`check_seed_coverage.py` requires a representative row for the new model. Add to
`scripts/seed_dev.py`:

- a **pending** join request against `fledgling`, so the staff queue has
  something in it;
- a seeded user who is a member of **no** tenant, so the door itself is
  reachable in dev without hand-editing the database.

Both idempotent, both tenant-scoped like the existing rows. Without the second,
the only way to see the join page is to delete your own membership.

### Docs

- [`docs/features/multitenancy.md`](../../features/multitenancy.md) — the
  section this plan has now rewritten twice. Final state: authorization is
  tenant-scoped **and** membership-gated; membership is acquired by a staff
  grant, a role grant, or an approved join request; `SUPER_ADMIN` bypasses;
  `public_page` routes do not.
- [`docs/reference/authentication.md`](../../reference/authentication.md) — the
  gate order in `_tenant_page`: tenant → feature → **membership** → role, and
  what each failure renders.
- [`docs/reference/data-model.md`](../../reference/data-model.md) —
  `TenantJoinRequest`, `JoinRequestStatus`, and the model count. The
  session-start hook checks this file against `models/`.
- [`docs/features/audit-logging.md`](../../features/audit-logging.md) and
  [`docs/features/event-system.md`](../../features/event-system.md) — the three
  join actions and event types.
- [`docs/current-state.md`](../../current-state.md) — new-community visibility
  is no longer a known issue.

## Wave 4 wrap-up

```bash
poetry run pytest
poetry run pytest tests/tenancy/
poetry run python scripts/audit_membership_coverage.py    # must report zero
scripts/ui_flag_sweep.sh
```

Then the audit's own scenario, end to end:

- Create a tenant, grant its first admin (wave 1), set it up (waves 1–3).
- As a platform user with **no roles and no membership** in it — the audit used
  `player_two` — open its home schedule. The measured behaviour was *"loaded the
  new community's home schedule, saw its first match with both players' names,
  and was offered Sign Up as commentator and tracker."* It must now be the join
  page.
- Request access; confirm staff are notified and the request appears in the
  queue with buttons.
- Approve; confirm the requester is notified, becomes a member, and lands on the
  page they originally asked for.
- Deny a second requester; confirm they are told, and that requesting again
  updates the same row.
- Confirm a public bracket URL still opens **signed out**.
- 390×844 for the join page and the staff queue.

Commit T4.1 separately — the backfill and its evidence are the record that this
was safe — then the gate as *"Gate a community on membership, and give everyone
else a door"*.

## After this wave

This directory and
[`docs/reviews/new-tenant-onboarding-ux.md`](../../reviews/new-tenant-onboarding-ux.md)
are deleted together. See [README.md](README.md#when-this-directory-is-finished)
for what has to be true first.

Two findings are deliberately **not** fixed by this plan and should be recorded
in `docs/current-state.md` rather than silently dropped:

- **The `System` service account** is offered as a person wherever it holds a
  membership (wave 2 T2.4). `User` has no service-account flag and inventing one
  was out of scope.
- **The 19-item admin drawer** on a brand-new community (RC1). Wave 1 supplies
  the ordering the audit found missing; nothing hides the tabs, deliberately.
