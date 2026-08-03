# Plan 3 — record prize splits in the app

**Read [README.md](README.md) first, including the ALTTPR payout block quoted
there. It is the specification.**

After every event, each tournament admin posts a payout block into their admin
thread and someone assembles them by hand. The handles live in a private Google
Sheet. This plan puts the split in the app and makes the block a button.

| Task | Size |
|---|---|
| T3.1 | The `PAYOUTS` flag | small |
| T3.2 | Model + migration | medium |
| T3.3 | Repository | small |
| T3.4 | `PayoutService` | large |
| T3.5 | Matcherino handle on the profile | small |
| T3.6 | Admin → Payouts tab | large |
| T3.7 | REST + MCP | medium |
| T3.8 | Seed + docs | medium |

The only plan in this directory with a new flag, a new model, a leak test and
required seed rows.

---

## T3.1 — The flag

`models/enums.py`, appended to `FeatureFlag`:

```python
    PAYOUTS = 'payouts'
```

`application/feature_flags.py`, a `FeatureFlagSpec` in a new `Operations`
category:

```python
        FeatureFlagSpec(
            FeatureFlag.PAYOUTS,
            'Prize Payouts',
            "Prize pool, placement splits and Matcherino handles for a "
            "tournament's winners, with an export for the payout run.",
            'Operations',
            service_modules=('application/services/payout_service.py',),
        ),
```

`established=False` — this is new, so it ships dark and no existing tenant is
backfilled.

Gated at four places, because hiding a tab is not gating:

1. `@requires_feature(FeatureFlag.PAYOUTS)` on every public `PayoutService`
   method: all mutations, plus `get_split` and `export_block`.
2. `and FeatureFlag.PAYOUTS in live` on the admin tab condition in
   `pages/admin.py:build_admin_tabs`.
3. `Depends(require_feature(FeatureFlag.PAYOUTS))` on the router in
   `api/__init__.py`, following the `TRIFORCE_TEXTS` mount at line 70.
4. The MCP read tool inherits the service guard.

`tests/test_feature_flags.py` fails until enum and registry agree.
`check_feature_flag_gating.py` fails if the declared `service_modules` do not
actually guard the flag.

---

## T3.2 — Model

`models/tournament.py`, two columns on `Tournament`:

```python
    # The advertised pool and the leaderboard bonus. Percentages apply to their
    # SUM: SGL's ALTTPR 2025 paid 50% of a $1000 pool plus a $100 bonus as $550.
    # Both nullable — a tournament with no prize money leaves them unset rather
    # than storing a zero that reads as "decided, and it's nothing".
    prize_pool = fields.DecimalField(max_digits=10, decimal_places=2, null=True)
    prize_bonus = fields.DecimalField(max_digits=10, decimal_places=2, null=True)
```

And the new model:

```python
class TournamentPayout(Model):
    """One placement's share of a tournament's prize pool.

    A row is a *share*, not a payment: ``place`` and ``percentage`` are stored
    and the money is computed as ``(prize_pool + prize_bonus) * percentage`` at
    read time. Storing the amount would be a second source of truth that drifts
    the moment the pool moves, which it does throughout the event.

    ``place`` is not unique. Joint placings are the normal case — SGL's ALTTPR
    2025 paid two third places at 10% each — and splitting a single 20% third
    place in half would hide the arithmetic from the admin checking it.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='payouts', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='payouts', on_delete=fields.CASCADE)
    place = fields.IntField()
    percentage = fields.DecimalField(max_digits=5, decimal_places=2)
    # Null while the split is drafted before the bracket finishes. SET_NULL so
    # retiring a user leaves the historical split intact and legible.
    entrant = fields.ForeignKeyField(
        'models.User', related_name='payouts', null=True, on_delete=fields.SET_NULL
    )
    note = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'tournamentpayout'
        unique_together = (('tournament', 'place', 'entrant'),)
        indexes = (('tournament',),)
```

`unique_together` on `(tournament, place, entrant)` rather than `(tournament,
place)`, so ties are legal. Postgres treats NULLs as distinct, so several
unfilled rows can sit at place 3 while the split is being drafted, and once both
are named the constraint stops one person being paid twice at one place.
`tournament` already implies the tenant, so the composite needs no `tenant`
column to be tenant-safe.

`Decimal`, not float and not integer cents: exact in Postgres, and it renders
straight into the UI and the Matcherino export without a conversion at either
edge. Every arithmetic path uses `decimal.Decimal`; a float anywhere near this
model is a bug.

Re-export from `models/__init__.py`.

```bash
poetry run aerich migrate --name add_tournament_payouts
poetry run aerich upgrade
```

**Read the generated migration.** One new table and three new columns
(`prize_pool`, `prize_bonus`, and `matcherino_username` from T3.5 if you do both
before migrating), nothing else. Check `git status migrations/` afterwards —
`aerich` computes its prefix from the `aerich` table's insertion order and has
been observed unlinking a colliding version file.

**Tenant consequences.** `TournamentPayout` carries a tenant FK, so
`tests/tenancy/test_leak_test_coverage.py` **fails** until it appears in an
isolation test (T3.8). Its BACKLOG is for pre-existing debt and may never grow.
`tests/test_seed_coverage.py` fails until the seed creates a row.

---

## T3.3 — Repository

`application/repositories/tournament_payout_repository.py`:

```python
class TournamentPayoutRepository(TenantScopedRepository[TournamentPayout]):
    model = TournamentPayout
```

inheriting the tenant-stamped `create` and scoped `get_by_id` from
`_base.py`, and adding:

- `list_for_tournament(tournament_id)` — scoped, `prefetch_related('entrant')`,
  ordered by `place` then `id` so ties render in a stable order.
- `replace_split(tournament, rows)` — delete-then-create inside one
  `in_transaction()`. A partial split is worse than the old one; do not write
  this as two awaited calls outside a transaction.

Export from `application/repositories/__init__.py`.

---

## T3.4 — `PayoutService`

New `application/services/payout_service.py`. Exported from
`application/services/__init__.py`.

| Method | Does |
|---|---|
| `get_split(tournament_id)` | rows with computed amounts |
| `set_pool(tournament_id, pool, bonus, actor)` | the two Tournament columns |
| `set_split(tournament_id, rows, actor)` | replace the whole split |
| `set_entrant(payout_id, user_id, actor)` | name a winner on a drafted row |
| `export_block(tournament_id)` | the text for the admin thread |

**Computation.** One place, used by every reader:

```python
total = (tournament.prize_pool or Decimal(0)) + (tournament.prize_bonus or Decimal(0))
amount = (total * row.percentage / Decimal(100)).quantize(Decimal('0.01'))
```

Round with `quantize`, not Python's `round`. Rounding is per row, so a split
whose percentages sum to 100 can still total a cent under the pool; that is
correct behaviour and belongs in the docstring rather than being fudged.

**Validation**, all raising `ValueError` so the UI notifies and REST 400s:

- percentages may not sum above 100
- a sum **below** 100 is allowed, because an unallocated remainder is real
- `place` at least 1
- `percentage` above 0
- pool and bonus not negative

**Authorization.** New `AuthService.can_manage_payouts(user, tournament)`,
following `can_edit_tournament` (line 242): STAFF, super-admin, or
`is_tournament_admin` for this tournament. That is deliberately who Rick asks
today, and it removes the relay rather than moving it.

**Audit and events.** Two new `AuditActions` and two mirrored `EventType`
members added to `EventType.ALL`:

```
TOURNAMENT_PRIZE_POOL_UPDATED = 'tournament.prize_pool_updated'
TOURNAMENT_PAYOUT_UPDATED     = 'tournament.payout_updated'
```

Both fired through `AuditService.write_and_publish` with
`event_extra={'tournament_id': ...}`. A hand-rolled `write_log` +
`event_bus.publish` pair is blocked by `check_dry_regressions.py`. Money moving
is exactly what an audit log is for; pass `actor` explicitly and never guard it
with `if actor:`.

`require_found(...)` for a missing tournament or payout row.

**The export.** `export_block` reproduces the block from the README verbatim,
because that is what gets pasted:

```
Total prize pool: $1000.00
Bonus: $100.00

1st place - Jem (Jem041#578236):            50% / $550.00
2nd place - ninjembro (Cody_Allyn#1102083): 30% / $330.00
```

A row with no `entrant` renders as `(unassigned)`. An entrant with no
`matcherino_username` renders the name alone with a trailing `(no Matcherino
handle)`, because a silently missing handle is what stalls a payout run.

---

## T3.5 — The Matcherino handle

`models/user.py`, beside the three verified links:

```python
    # Self-entered, unlike the OAuth-verified links above, so deliberately NOT
    # unique: a typo under a unique constraint would lock the rightful owner out
    # of their own handle. Format is Matcherino's ``name#id``.
    matcherino_username = fields.CharField(max_length=255, null=True)
```

`User` is global with no tenant FK, which is correct here: someone who wins in
two communities has one Matcherino account.

Surfaced on `pages/home_tabs/player_edit_info.py` in the connected-accounts
area, rendered as a plain text field and visually distinct from the
Challonge/Twitch/racetime links so nobody reads it as verified. `_link_section`
handles the verified three; this is not one of them and should not borrow their
chrome. Written through `UserService`, not directly.

---

## T3.6 — Admin → Payouts

New `pages/admin_tabs/admin_payouts.py`. Follow
`pages/admin_tabs/admin_webhooks.py`, the closest working example of a CRUD tab
that gets the table contract right.

A table of the tournaments this actor may manage: name, pool, bonus, total,
whether a split exists and whether every place has an entrant. Row action opens
the split editor, built on `theme/dialog/_helpers.py`. A **Copy for Matcherino**
button puts `export_block` on the clipboard.

Required by the hooks, not optional:

- `enable_mobile_grid(table, columns, actions=..., table_key=TableKeys.ADMIN_PAYOUTS)`
- a new `ADMIN_PAYOUTS = 'admin.payouts'` entry in `TableKeys`
  (`theme/tables/preferences.py`)

Registered in `pages/admin.py:build_admin_tabs` under the `Operations` group:

```python
    if (is_staff or is_ta_any) and FeatureFlag.PAYOUTS in live:
```

`can_view_admin` already admits a bare tournament admin
(`auth_service.py:152`), so no authorization change is needed for a TA to reach
this tab. A TA sees only their own tournaments; the service refuses the rest,
and the tab must not offer rows whose controls will refuse.

Sort money columns numerically, not on the rendered string.

---

## T3.7 — REST and MCP

`api/routers/payouts.py`, schemas in `api/schemas/payouts.py`:

| Route | |
|---|---|
| `GET /api/tournaments/{id}/payouts` | split with computed amounts |
| `PUT /api/tournaments/{id}/payouts` | replace the split |
| `PUT /api/tournaments/{id}/prize-pool` | pool and bonus |

Mounted in `api/__init__.py` with
`dependencies=[Depends(require_feature(FeatureFlag.PAYOUTS))]`.

Services raise `NotFoundError`, which `ServiceErrorRoute` turns into a 404, so
**no `_load_*_or_404` preload in the router** — the DRY hook blocks new ones.
Money fields serialise as strings, not floats.

MCP: one read tool, `get_tournament_payouts`, in the existing read set
(`mcpserver/tools/`). No write tool in this plan; the MCP write surface is
opt-in at consent and prize money is not where to extend it first.

---

## T3.8 — Seed, tests, docs

**Seed** (`scripts/seed_dev.py`, idempotent `get_or_create`, tenant-threaded):

- one finished tournament with a pool, a bonus, and the full 50/30/10/10 split
  including **two named third places**, so the tie path has a fixture
- one active tournament with a pool and no split rows, which is the drafting
  state
- two seeded users with a `matcherino_username`, and one winner deliberately
  without, so the export's missing-handle branch renders in the running app
- `PAYOUTS` available and enabled for `default`, and **absent for the second
  tenant** — the isolation test needs that asymmetry, and so does
  `ui_flag_sweep.sh`

**Tests:**

`tests/services/test_payout_service.py`
- 50% of a $1000 pool plus a $100 bonus is $550, the arithmetic this feature
  was specified from
- the tie case: two rows at place 3, 10% each, both $110
- percentages summing above 100 raise
- summing below 100 is accepted
- a drafted row with no entrant computes its amount anyway
- a tournament admin may edit their own tournament and not another's
- flag off raises `FeatureDisabledError`
- `export_block` output matches the expected text exactly, including the
  missing-handle line

`tests/tenancy/test_payout_tenant_isolation.py`
- reads scoped, writes stamped with `current_tenant_id()`
- a cross-tenant read returns nothing rather than another community's split

`tests/api/test_payouts_api.py` — the full matrix: 401 unauthenticated, 403
wrong role, 403 read-only token, 404 unknown id, 404 cross-tenant, 404 flag off.

Factories and hoisted conftest fixtures only. No network; the socket guard will
fail it.

**Docs:**

- new `docs/features/payouts.md` — the model, the computation, who may edit,
  the export, and why amounts are not stored
- `docs/reference/data-model.md` — model, ERD, the two Tournament columns,
  `User.matcherino_username`
- `docs/reference/services.md`, `docs/reference/rest-api.md`
- `docs/features/feature-flags.md` — the registry row
- `docs/features/mcp-server.md` — the read tool
- `docs/current-state.md` — capability table
