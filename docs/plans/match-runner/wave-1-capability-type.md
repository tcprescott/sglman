# Wave 1 — introduce the runner, collapse the service-layer checks

**Read [README.md](README.md) first.**

Pure refactor. No migration, no behaviour change, no new capability. At the end
of this wave the four service/repository sites ask a runner for a capability
instead of testing `is_racetime_enabled`, and the runner is resolved in exactly
one place.

| Task | Touches | Size |
|---|---|---|
| T1.1 | the runner type + registry | medium |
| T1.2 | `Tournament.runner`, and a queryable predicate | small |
| T1.3 | the three service checks | small |
| T1.4 | the repository filter | small |
| T1.5 | docs | small |

---

## T1.1 — The runner type and its registry

### Where it lives, and why

`models/match_runner.py`, exported from `models/__init__.py`.

It is a **domain concept**, not a service: it holds no state, performs no I/O,
and both `models/` and every layer above it must be able to import it without
creating a cycle. Putting it under `application/services/` would make
`models/tournament.py` import a service to answer a question about itself.

It must not import from `application/` at all. If a capability seems to need a
service call, it does not belong on the runner — the *caller* does the work and
asks the runner only what is allowed.

### The type

```python
"""How a match is run.

`Tournament.racetime_bot` used to be the only answer to four different
questions: who seats players, whether physical stations exist, who owns the
seed, and whether a human drives the match at all. Those are capabilities, and
they are not all implied by one integration — an online match with no bot needs
a human to start it but has no stations to assign.

Runners answer capability questions only. Nothing outside this module should
compare a runner's ``key`` or use ``isinstance``; ask what it can do.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MatchRunner:
    key: str
    label: str

    #: A human seats players before the match can start.
    checks_in_players: bool
    #: Physical seats exist at the venue.
    assigns_stations: bool
    #: Something other than Wizzrobe rolls and holds the seed.
    owns_seed: bool
    #: An external system stamps started/finished; no human presses the buttons.
    drives_lifecycle: bool
    #: An external system reports who won.
    reports_result: bool

    @property
    def needs_a_person(self) -> bool:
        """True when a human has to drive this match to completion.

        The proctor board's membership test. Deliberately derived rather than
        declared: a runner that neither drives the lifecycle nor reports the
        result needs somebody, whatever else is true of it.
        """
        return not (self.drives_lifecycle and self.reports_result)


ONSITE = MatchRunner(
    key='onsite', label='On-site (proctored)',
    checks_in_players=True, assigns_stations=True,
    owns_seed=False, drives_lifecycle=False, reports_result=False,
)

RACETIME = MatchRunner(
    key='racetime', label='racetime.gg',
    checks_in_players=False, assigns_stations=False,
    owns_seed=True, drives_lifecycle=True, reports_result=True,
)

RUNNERS = {r.key: r for r in (ONSITE, RACETIME)}
DEFAULT_RUNNER = ONSITE
```

Frozen dataclass so a runner cannot be mutated at runtime and the instances can
be module-level singletons.

### Refusal messages

Two hardcoded strings currently name racetime; T1.3 replaces them, so the runner
has to supply them. Add one method rather than a field per refusal:

```python
    def refuse(self, action: str) -> str:
        """Why ``action`` is unavailable under this runner."""
        return f"{self.label} matches do not support {action}."
```

Then override per runner where a better sentence exists — keep the current
wording for racetime so today's messages do not regress:

```python
_REFUSALS = {
    ('racetime', 'check-in'):
        "Check-in is disabled for racetime.gg tournaments — the race room "
        "manages the match lifecycle.",
    ('racetime', 'station assignment'):
        "Station assignment is disabled for racetime.gg tournaments — players "
        "race remotely, so there are no on-site stations to assign.",
}
```

and have `refuse` consult it, falling back to the generic sentence. A dict keyed
by `(key, action)` keeps the copy together and readable; a subclass per runner
would be four classes to hold two strings.

### Tests

`tests/models/test_match_runner.py` (create the directory if absent):

```python
def test_every_registered_runner_has_a_unique_key()
def test_onsite_needs_a_person()
def test_racetime_does_not_need_a_person()
def test_racetime_keeps_its_existing_refusal_wording()   # exact string match
def test_refuse_falls_back_to_a_generic_sentence()
def test_runners_are_immutable()                          # dataclasses.FrozenInstanceError
```

The exact-string test matters: it is what stops T1.3 from silently changing a
user-facing message while "just refactoring".

---

## T1.2 — Resolve the runner, and make it queryable

**Depends on:** T1.1.

### Files

- `models/tournament.py`
- `application/repositories/match_repository.py` (the constant only; the filter
  is T1.4)

### Change 1 — the property

`models/tournament.py`, beside `is_racetime_enabled`:

```python
    @property
    def runner(self) -> MatchRunner:
        """How this tournament's matches are run.

        Derived, not stored: today the only signal is whether a racetime bot is
        attached. A ``runner_key`` column arrives when a runner exists that
        cannot be derived (see the match-runner plan, wave 4).
        """
        return RACETIME if self.racetime_bot_id else ONSITE
```

**Use `racetime_bot_id`, not `racetime_bot`** — the `_id` attribute is present
on a plain fetch, while the relation attribute triggers a lazy load and raises
outside an awaited context. `is_racetime_enabled` should be rewritten in terms
of `runner` rather than the reverse, so there is one derivation:

```python
    @property
    def is_racetime_enabled(self) -> bool:
        """Deprecated: prefer ``runner``. Kept for callers outside this plan."""
        return self.runner is RACETIME
```

Do **not** delete `is_racetime_enabled` in this wave — the racetime services,
the SpeedGaming ETL and the online-tournament pages all read it, and they are
out of scope here. Deleting it is wave 3's cleanup, once every caller is known.

### Change 2 — the SQL-side predicate

The whole point of the "no queryable representation" symptom. Add to
`application/repositories/match_repository.py` (or a shared query-helpers module
if one exists — check first):

```python
# The ORM cannot filter on ``Tournament.runner``: it is a Python property. These
# express each runner as the query that selects it, so a caller never open-codes
# ``racetime_bot_id__isnull`` again. Wave 4 replaces the bodies with a
# ``runner_key`` comparison and leaves every caller untouched — which is the
# point of routing through here.
RUNNER_FILTERS = {
    'onsite':   {'tournament__racetime_bot_id__isnull': True},
    'racetime': {'tournament__racetime_bot_id__isnull': False},
}

NEEDS_A_PERSON_FILTER = RUNNER_FILTERS['onsite']
```

`NEEDS_A_PERSON_FILTER` is what T1.4 uses. It happens to equal the on-site
filter today; naming it separately is what lets wave 4 widen it to two runners
without hunting for call sites.

### Tests

`tests/models/test_match_runner.py`:

```python
def test_tournament_with_a_racetime_bot_runs_on_racetime()
def test_tournament_without_one_is_onsite()
def test_is_racetime_enabled_agrees_with_runner()   # both directions
```

Use a `SimpleNamespace`-style fake or an unsaved `Tournament(...)` — the
property reads `racetime_bot_id` only, so no DB is needed. Add one DB-backed
test that `RUNNER_FILTERS` actually selects what it claims.

---

## T1.3 — Replace the three service checks

**Depends on:** T1.2.

### Files

- `application/services/match/match_schedule_service.py` (`seat_match`)
- `application/services/match/match_service.py` (`assign_stations`)
- `application/services/match/match_display_service.py` (the row dict)

### Change 1 — check-in

`seat_match` currently reads:

```python
        if match.tournament and match.tournament.is_racetime_enabled:
            raise ValueError(
                "Check-in is disabled for racetime.gg tournaments — the race "
                "room manages the match lifecycle."
            )
```

becomes:

```python
        runner = match.tournament.runner if match.tournament else DEFAULT_RUNNER
        if not runner.checks_in_players:
            raise ValueError(runner.refuse('check-in'))
```

Note the fallback: a match with no tournament keeps today's behaviour (the old
condition was false, so check-in was allowed). `DEFAULT_RUNNER` is on-site,
whose `checks_in_players` is `True`, so it still is. Do not "improve" this into
a rejection — it is a behaviour change, and not this wave's.

### Change 2 — stations

`assign_stations`, same shape, `runner.assigns_stations` and
`runner.refuse('station assignment')`.

### Change 3 — the row dict

`_format_match_for_display` currently emits `is_racetime`. **Keep that key** in
this wave and add the capability keys beside it; wave 2 removes it once the
templates stop reading it. Emitting both for one wave is what lets waves 1 and 2
ship independently.

```python
            # How this match is run, as capabilities rather than an integration
            # name — the templates gate controls on these. ``is_racetime`` is
            # retained until the templates are converted (match-runner wave 2).
            'is_racetime': match.tournament.is_racetime_enabled if match.tournament else False,
            'runner': {
                'key': runner.key,
                'checks_in_players': runner.checks_in_players,
                'assigns_stations': runner.assigns_stations,
                'owns_seed': runner.owns_seed,
                'needs_a_person': runner.needs_a_person,
            },
```

Resolve `runner` once above the dict. Only the flags the templates need go on
the wire — `drives_lifecycle` and `reports_result` are server-side concerns.

### Tests

`tests/services/test_match_service.py` and
`tests/services/test_match_display_service.py`:

```python
async def test_seat_match_is_refused_when_the_runner_does_not_check_in(db)
async def test_assign_stations_is_refused_when_the_runner_has_no_stations(db)
def test_row_carries_runner_capabilities()
def test_row_still_carries_is_racetime_for_now()
```

The first two must assert on the **exact existing message**, so a refactor
cannot quietly reword a user-facing string. `test_match_display_service.py` is a
pure/`SimpleNamespace` file — follow its style rather than reaching for `db`.

---

## T1.4 — Route the board filter through the predicate

**Depends on:** T1.2.

### Files

- `application/repositories/match_repository.py`
- `application/services/match/match_display_service.py`

### Change

`MatchRepository.get_all` takes `exclude_racetime: bool = False` and does:

```python
        if exclude_racetime:
            query = query.filter(tournament__racetime_bot_id__isnull=True)
```

Rename the parameter to `only_needs_a_person: bool = False` and use the
constant:

```python
        if only_needs_a_person:
            query = query.filter(**NEEDS_A_PERSON_FILTER)
```

Thread the rename through `MatchDisplayService.get_matches_for_display` and its
one caller, `MatchTableView` (`exclude_racetime=True` is passed only by
`pages/volunteer_tabs/proctor_station.py`). The `MatchTableView` constructor
parameter should be renamed too — the proctor board is asking "does this need
me?", which is what the new name says and the old one only approximated.

Keep the comment explaining that the ORM cannot filter a Python property.

### Tests

Update the existing `test_exclude_racetime_omits_racetime_tournament_matches`
in `tests/services/test_match_display_service.py` to the new name and add:

```python
async def test_only_needs_a_person_keeps_onsite_matches(db)
```

Note that the existing test builds a racetime tournament with a `RacetimeBot` +
`racetime_bot=` FK — there is no `is_racetime_enabled=` kwarg. Follow that.

---

## T1.5 — Docs

- `docs/reference/data-model.md` — a short section on `MatchRunner`: what the
  capabilities mean, that resolution is derived from `racetime_bot_id` for now,
  and that `Tournament.is_racetime_enabled` is retained but deprecated in favour
  of `Tournament.runner`.
- `docs/reference/services.md` — note that `seat_match` / `assign_stations`
  refuse via the runner, and that the refusal wording comes from the runner.
- `docs/features/online-tournaments.md` — one line: a racetime tournament is
  the `racetime` runner, which owns the seed and drives the lifecycle.

## Wave 1 wrap-up

```bash
poetry run pytest
grep -rn "is_racetime_enabled" --include=*.py application/services/match/ \
    application/repositories/
```

That grep should return only `match_display_service.py`'s retained
`is_racetime` key. Hits anywhere else in those two trees mean a call site was
missed.

Then browser-verify all four surfaces at both widths. **Nothing should look any
different** — that is the acceptance criterion for a pure refactor. The proctor
board must still exclude racetime matches, racetime rows must still say
"racetime.gg" and offer no check-in, and the station picker must still refuse a
racetime match with the same sentence.

Commit as *"Make how a match is run a first-class type"*.
