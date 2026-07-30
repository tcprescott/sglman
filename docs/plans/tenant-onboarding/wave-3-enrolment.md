# Wave 3 — enrolment gets a surface, and a working write

**Read [README.md](README.md) first.**

No migration, no authorization change. This wave fixes the thing the audit
called the *"path of least resistance"* — that the only discoverable way to get
players into a new community's tournament is a checkbox whose real effect is
invisible — and, on the way, a tenant-stamping bug in the enrolment write that
the test suite is structurally unable to see.

Fixes audit findings **F3** (arbitrary silent enrolment), **F4** (the largest
form in the app), and root cause **RC3**.

| Task | Touches | Size |
|---|---|---|
| T3.1 | The unstamped enrolment write, and the blind spot that hid it | medium |
| T3.2 | `TournamentPlayersDialog` becomes read-write | medium |
| T3.3 | "Choose any players" says what it does | small |
| T3.4 | Add Tournament: progressive disclosure | medium |
| T3.5 | Seed + docs | small |

**T3.1 is a bug fix and ships first.** It is independent of the rest and should
be its own commit — do not bury it in a UI wave's squash.

---

## T3.1 — The enrolment write does not stamp a tenant

### What was found

`TournamentPlayers.tenant` is a **non-null** FK
([`models/tournament.py:114`](../../../models/tournament.py#L112)). Two writes in
`UserService` omit it:

```python
# application/services/user_service.py:213  (update_user_tournament_registrations)
await TournamentPlayers.create(user=user, tournament=tournament)

# application/services/user_service.py:363  (manage_tournament_enrollments)
await TournamentPlayers.create(user=user, tournament=tournament)
```

Compare `TournamentRepository`, which stamps correctly at
[lines 216](../../../application/repositories/tournament_repository.py#L216) and
[320](../../../application/repositories/tournament_repository.py#L320):
`TournamentPlayers.create(tenant_id=current_tenant_id(), ...)`.

These two are the per-user edit dialog's enrolment path — the first of the three
routes the audit lists under RC3, and the one it did **not** drive. The route it
did drive ("Choose any players") goes through the repository and stamps
correctly, which is why the audit saw enrolment succeed.

### Why nothing caught it

Three independent safety nets each miss it, and the reasons are worth knowing
before adding a fourth:

1. **The test fixture stamps the tenant.** `tests/conftest.py`'s `db` fixture
   *"wraps every tenant-scoped model's `.create` to stamp that tenant when a
   caller omits it"*, and its docstring is explicit that this is a harness
   convenience while *"the production `never auto-stamp` contract stays
   intact"*. Any DB-backed test of this path therefore passes.
2. **The unit tests mock the write.**
   `tests/services/test_user_service.py::TestUpdateUserTournamentRegistrations`
   monkeypatches `TournamentPlayers.create` to an `AsyncMock` and asserts set
   math against `await_count`. The kwargs are never inspected.
3. **The hook only reads repositories.** `check_tenant_scoping.py`'s docstring
   lists *"queries built outside a repository module"* as a deliberate miss —
   precision over recall. A direct ORM write in a **service** is exactly that
   blind spot.

**Confirm before fixing.** The above is verified by reading; that the insert
actually fails was *not* run against Postgres — the suite is SQLite. Reproduce
first: enrol a user through the Users tab's edit dialog on the running app
(README's verification loop), and record what happens. If it raises, this is a
production bug on a documented path. If Postgres somehow accepts it, the row is
still orphaned across every scoped query, which is the same fix with a quieter
symptom.

### The fix

Both writes belong in the repository that already does this correctly. Route
them through `TournamentRepository`'s existing enrolment method rather than
adding `tenant_id=` at the two service call sites — a service reaching for
`Model.create` is the layering violation that let this happen, and stamping it
in place preserves the shape that will reproduce the bug next time.

`UserService` already holds a `repository`; check whether it can reach
`TournamentRepository` without a cycle, and if not, inject it the way the
service's other collaborators are.

### Closing the blind spot

A fix without a guard invites the identical bug in the next service. Do both:

**Widen the hook.** `check_tenant_scoping.py` inspects repository modules; extend
it to flag a `WRITE_ROOTS` call on a tenant-scoped model **in a service module**
with no tenant kwarg. The existing escape-hatch convention
(`cross-tenant` / `unscoped` / `global` in the function source) carries over
unchanged, and `EXEMPT_MODELS` still applies. Services legitimately write
through repositories, so the true-positive rate should be high — but run it
across `application/services/` before committing and report what else it finds.
**If it flags pre-existing writes beyond these two, list them and fix them in
this task** rather than exempting them to keep the hook quiet.

**Make the fixture's help visible.** The `db` fixture's auto-stamp is the right
call for ~700 legacy call sites, but it means no DB test can ever catch an
unstamped write. Add one test that opts out — a fixture flag, or a direct
`Model.create` outside the wrapper — asserting that the enrolment path stamps
the tenant *itself*:

```python
async def test_enrolment_stamps_the_tenant_without_the_fixtures_help(db)
```

That is the test that must fail without the fix; say so explicitly if the
fixture's design makes it impossible, and fall back to asserting the repository
call is made with `tenant_id`.

### Tests

```python
async def test_update_registrations_creates_a_tenant_stamped_row(db)
async def test_manage_enrollments_creates_a_tenant_stamped_row(db)
async def test_enrolment_rows_do_not_leak_across_tenants(db)   # tests/tenancy/
```

The existing mocked tests stay — the set math they cover is real. Add
`create_mock.assert_awaited_with(...)`-style kwarg assertions to them so a
future refactor cannot drop the stamp again while the mocks still pass.

---

## T3.2 — The entrants dialog becomes read-write

**Depends on:** T3.1 (do not build a surface on a broken write), wave 2's
member scoping.

### The measurement

The Tournaments tab's caption invites the user to *"click a name to edit, or a
player count to manage entrants"*, and
[`theme/dialog/tournament_players_dialog.py`](../../../theme/dialog/tournament_players_dialog.py)
is **27 lines of read-only list plus a Close button**. The caption promises
management; the dialog delivers a list. This is the same shape as F2's Users
caption — the copy already describes the right behaviour and the code does not.

### Files

- `theme/dialog/tournament_players_dialog.py`
- `application/services/tournament_service.py` (an enrol/unenrol pair, if one
  is not already there under another name — check
  `manage_tournament_enrollments` first before adding)

### The change

Keep the dialog small. It needs:

- The current entrants, as today, plus a **Remove** action each.
- An **Add** select over `UserService.get_community_users()` — wave 2's
  member-scoped list, which is the whole reason this dialog is safe to make
  writable now. Before wave 2 an "add entrant" picker would have offered every
  user on the platform, which is the bug the audit found in the *other*
  enrolment route.
- Nothing else. No bulk import, no CSV, no invite. This is the tournament-centric
  surface RC3 says is missing, not a new subsystem.

The service does the writing and the auditing; the dialog catches `ValueError`
and calls `ui.notify(str(e), color='warning')`. `enforce_no_orm_writes.py` will
block anything else.

### Audit + events

Enrolment changes are already audited under
`AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED`. Reuse it — do not introduce a
parallel action for the same fact reached from a different screen; that is how
an audit log stops being answerable. If the existing details dict does not
identify the tournament, extend it rather than forking the action.

### Tests

```python
async def test_entrants_can_be_added_and_removed(db)
async def test_adding_a_non_member_is_refused(db)
async def test_entrant_changes_are_audited(db)
```

The second is the wave-2 dependency made explicit: the service must refuse, not
merely the picker omit. UI-only gating is not gating.

---

## T3.3 — "Choose any players" says what it does

**Depends on:** wave 2 T2.4 (which relabels the checkbox).

### The measurement

F3: ticking the box turned the Players select from 0 options into 11 — *"every
`User` row on the platform, `System` included"* — and creating the match
**silently enrolled** the chosen players into the tournament. The audit ties
this to match-operations F8, so it is a known, twice-found behaviour.

Wave 2 fixed *who* is offered. This task fixes *what happens next*.

### Files

- `theme/dialog/match_dialog.py` — the checkbox at
  [line 451](../../../theme/dialog/match_dialog.py#L451) and
  `update_selection_options` at
  [470-483](../../../theme/dialog/match_dialog.py#L470)
- whichever service performs the create-time enrolment (find it from
  `MatchService`; it will be a `TournamentPlayers` write on the match-create
  path)

### The change

The side effect is **not wrong** — scheduling someone into a tournament they are
not enrolled in genuinely should enrol them, or the match refers to a
non-entrant. What is wrong is that it is invisible. Make it visible:

1. Under the checkbox, once it is ticked and players are chosen, a caption
   naming the consequence: *"2 players will be enrolled in <tournament>."*
   Compute it from the selection, not a static sentence, so it says nothing when
   everyone chosen is already enrolled.
2. In the success notification, say so: *"Match created — Alice and Bob were
   enrolled in Spring Open."* The audit's measured notification was a bare
   *"Match created successfully"*.

No confirmation dialog. The reviews' cross-cutting theme is that
*"confirmation is spent on the reversible actions"* — enrolment is reversible
from T3.2's dialog, and a modal here would add a click to the common path to
protect against a cheap mistake.

### Tests

```python
def test_enrolment_preview_names_only_the_not_yet_enrolled()
def test_enrolment_preview_is_empty_when_everyone_is_enrolled()
async def test_match_create_notification_reports_enrolments(db)
```

---

## T3.4 — Break up the Add Tournament wall

**Depends on:** nothing.

### The measurement

F4: **1,730 px tall, 21 inputs, 4 selects, 5 checkboxes**, of which *exactly one
field is required*. The audit's point is not that the fields are wrong — it is
that *"nothing distinguishes 'fill this now' from 'come back to this when you
care', so the cheapest correct action (type a name, save) looks like the
riskiest one."*

### Files

- [`theme/dialog/tournament_edit_dialog.py`](../../../theme/dialog/tournament_edit_dialog.py)
  (400 lines; the field block runs from
  [line 65](../../../theme/dialog/tournament_edit_dialog.py#L65))

### The change

Group the existing controls behind `ui.expansion` sections, **collapsed by
default on create and expanded on edit** — a new community sees a short form; an
admin returning to configure racetime does not have to hunt.

Read the current fields before grouping; from the source they fall out roughly
as:

| Section | Fields | Default |
|---|---|---|
| *(ungrouped, always visible)* | name, description, active | open |
| **Scheduling** | average/max match duration, players per match, team size, tournament days/hours | collapsed |
| **Entry & administration** | staff-administered, allow requests, rules URL, format | collapsed |
| **Seeds & randomizer** | seed generator, preset, triforce access message | collapsed |
| **Integrations** | Challonge, racetime bot/profile/goal and its four sub-controls, bracket URL | collapsed |

Do not change any field's semantics, defaults, or validation in this task — it
is a layout change, and mixing a behaviour change into it makes the diff
unreviewable. If a default looks wrong while you are in there, note it for the
wrap-up rather than fixing it.

Give the name field a hint saying the rest can wait: *"Everything below has a
sensible default — you can come back to it."* That single sentence is most of
what F4 asks for.

### Mobile

Expansions help the 390 px case most; re-measure the collapsed height there and
record it in the commit message next to the audit's 1,730 px, so the improvement
is on the record the same way the problem was.

### Tests

Layout, so the check is a screenshot. Add the one assertion worth automating:

```python
def test_only_the_name_field_is_required()
```

which pins the audit's finding that one field is required, so a later change
that quietly makes a collapsed field mandatory — invisible, inside a collapsed
section — fails loudly.

---

## T3.5 — Seed and docs

### Seed

Wave 1's `fledgling` tenant deliberately has no tournament. Once T3.2 exists,
the state worth adding is **a tournament with zero entrants** — that is the
state the new entrants dialog is for, and the one the checklist's `enrolment`
step reports outstanding.

Put it in `fledgling` only. The populated tenants keep their entrants, so a
reviewer gets both the empty and the full dialog from one seed run.

### Docs

- [`docs/reference/frontend.md`](../../reference/frontend.md) — the entrants
  dialog is now read-write; the Add Tournament dialog is sectioned.
- [`docs/reference/services.md`](../../reference/services.md) — the enrolment
  write routes through `TournamentRepository`; note the three enrolment entry
  points and that they share one audit action.
- [`.claude/README.md`](../../../.claude/README.md) — the widened
  `check_tenant_scoping.py` scope, if T3.1's hook change lands.
- [`docs/development.md`](../../development.md) — a short note that the `db`
  fixture auto-stamps tenants and what that means for testing a write path. A
  future reader who finds a stamping bug should not have to re-derive why the
  suite was green.

## Wave 3 wrap-up

```bash
poetry run pytest
poetry run pytest tests/tenancy/
grep -rn "TournamentPlayers.create" --include=*.py application/services/
```

That grep should return **nothing** — both service-level writes are now in the
repository.

Then, on a freshly created tenant with a tournament and no entrants:

- Enrol someone through the **Users tab edit dialog** — the path T3.1 fixes.
  Confirm it works against Postgres, which is the whole point of the task.
- Open the tournament's player count, add and remove an entrant, and confirm a
  non-member cannot be added.
- Schedule a match with "Include players not enrolled in this tournament" and
  confirm the enrolment is stated before and after.
- Add Tournament at 1500 px and 390×844; record the collapsed height.

Commit T3.1 separately as *"Stamp the tenant on the enrolment write, and let the
hook see service-layer writes"*, then the rest as *"Give enrolment a home on the
tournament it belongs to"*.
