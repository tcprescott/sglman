# Wave 4 — a third runner, and making runners selectable

**Read [README.md](README.md) first. Waves 1–3 must be merged.**

The payoff. Everything so far has been derivable from `racetime_bot_id`, which
means there have only ever been two runners. This wave adds one that cannot be
derived, which forces the column — and closes a gap that exists today.

| Task | Size |
|---|---|
| T4.1 | `runner_key` column + migration + backfill | medium |
| T4.2 | the `manual_remote` runner | small |
| T4.3 | admin UI to choose a runner | medium |
| T4.4 | seed: one tournament per runner | small |
| T4.5 | docs | small |

---

## The gap being closed

`Tournament` has **no on-site/online field**. The only signal is whether a
racetime bot is attached. So *"online, but a human runs it"* is inexpressible:

- Players are remote, so there are no stations to assign.
- But nobody is opening a race room, so a human must start and finish it and
  type in the winner.

Today such a tournament is treated as fully on-site and offered a station
picker for seats that do not exist. That is a real defect now, independent of
any future third-party tool.

---

## T4.1 — Store the runner

### Model

`models/tournament.py`:

```python
    # How this tournament's matches are run. Nullable rather than defaulted so
    # an untouched tournament keeps deriving from ``racetime_bot`` — see the
    # resolution order in ``runner``.
    runner_key = fields.CharField(max_length=32, null=True)
```

```bash
poetry run aerich migrate --name add_tournament_runner_key
poetry run aerich upgrade
```

**Read the generated migration before continuing.** It must add exactly one
nullable column. If it contains anything else, the working tree has unrelated
model drift — stop and investigate.

> **Migration numbering hazard, learned the hard way.** `aerich migrate` unlinks
> any existing version file that shares the numeric prefix it computes, and it
> computes that prefix from the `aerich` table's *insertion order*, not the
> filename. On a branch where migrations were renumbered after a merge, it has
> silently deleted an existing migration file. After generating, run
> `git status migrations/` and confirm the only change is your new file.

### Resolution order

```python
    @property
    def runner(self) -> MatchRunner:
        """How this tournament's matches are run.

        Explicit choice wins; otherwise derive. The derivation stays because a
        racetime bot is unambiguous — attaching one *is* choosing that runner —
        and because it keeps every pre-existing tournament correct without a
        data migration that would have to guess.
        """
        if self.runner_key and self.runner_key in RUNNERS:
            return RUNNERS[self.runner_key]
        return RACETIME if self.racetime_bot_id else ONSITE
```

An unknown `runner_key` falls through to derivation rather than raising — a
tenant on an older deploy after a downgrade must not get a 500 on the schedule
page. Log it once at warning level if you like, but do not raise.

### The queryable side

`RUNNER_FILTERS` and `NEEDS_A_PERSON_FILTER` (wave 1) now need to honour the
column. This is the moment the wave-1 indirection pays off — the callers do not
change:

```python
RUNNER_FILTERS = {
    'onsite': {'tournament__runner_key': 'onsite'},
    ...
}
```

except that a null `runner_key` still means *derive*, so each filter is a
disjunction: explicitly-mine, **or** null-and-I-am-what-derivation-yields. Build
these with `Q` objects. Get this right — a tournament with `runner_key=NULL` and
no bot must still match the on-site filter, or every existing tournament falls
off the proctor board.

`NEEDS_A_PERSON_FILTER` becomes the union of `onsite` and `manual_remote`.

**Test this specifically, with all four combinations**: null/on-site, null/bot,
explicit/on-site, explicit/manual_remote. This is the single highest-risk change
in the plan, because getting it wrong silently empties a board.

---

## T4.2 — The `manual_remote` runner

`models/match_runner.py`:

```python
MANUAL_REMOTE = MatchRunner(
    key='manual_remote', label='Online (manually run)',
    checks_in_players=True,      # a human confirms both players showed up
    assigns_stations=False,      # they are at home; there are no seats
    owns_seed=False,             # we roll it and DM it
    drives_lifecycle=False,      # a human starts and finishes it
    reports_result=False,        # a human types in the winner
)
```

Add to `RUNNERS`. That is the whole runner — which is the point of waves 1–2: a
new way of running matches is a five-field declaration, and every gate,
template, filter and refusal message follows from it with no further edits.

**Verify that claim rather than assuming it.** Create a `manual_remote`
tournament in dev and confirm without touching any other file that its matches:

- offer Check In and the lifecycle buttons
- offer **no** Assign Stations
- **do** offer seed Generate
- appear on the proctor board (it needs a person)
- say "Online (manually run)" nowhere it should say "racetime.gg"

If any of those needs a code change, wave 2 left a hardcoded assumption behind —
fix it there and note it.

---

## T4.3 — Let an admin choose

### Files

- `theme/dialog/tournament_dialog.py` (find the real name — the tournament
  create/edit dialog)
- `application/services/tournament_service.py`
- `api/schemas/tournaments.py`, and the tournament router

### Change

A select on the tournament dialog listing `RUNNERS` by `label`, bound to
`runner_key`, with a blank "Automatic" option meaning null/derive. Put it near
the racetime configuration, since the two interact.

Guard the combination in the **service**, not just the dialog: attaching a
racetime bot while `runner_key='onsite'` is contradictory. Decide one of:

- refuse the combination with a `ValueError`, or
- let the explicit key win and say so in the field's help text.

Refusing is safer and easier to explain. Either way it belongs in
`TournamentService`, because the REST route reaches the same field.

Audit the change (`AuditActions.TOURNAMENT_UPDATED` already exists and is in
`_EVENT_CANDIDATES`), and include the old and new key in the details — changing
how a tournament is run mid-event is exactly the kind of thing someone will need
to reconstruct afterwards.

### REST

Add `runner_key` to the tournament response and update schemas. It is a
capability-bearing field; the MCP tournament tool should expose it read-only
too if it enumerates fields explicitly.

---

## T4.4 — Seed one tournament per runner

The seed already separates on-premises from racetime fixtures. Generalise it to
the convention in the README: **one tournament per runner**, named for how it is
run, holding only matches that runner can reach.

Add a `manual_remote` tournament with a couple of matches — one scheduled, one
started — and give it `seed_generator` set, since the interesting thing about
this runner is that it rolls a seed but has no stations.

Keep each fixture honest: no race room on a manually-run tournament, no station
assignments on a remote one, no proctor-lifecycle matches on the racetime one.
A fixture that cannot occur in production teaches the wrong thing and hides
bugs.

After seeding, print the tournament/runner/match-count table and check it reads
the way you would explain it to someone.

---

## T4.5 — Docs

- `docs/reference/data-model.md` — `runner_key`, the resolution order, and why
  it is nullable.
- `docs/features/online-tournaments.md` — the three runners as a table, and
  specifically that "online" is not synonymous with "racetime".
- `docs/reference/rest-api.md` — the new field.
- `docs/development.md` — the seed's one-tournament-per-runner convention, if it
  describes the fixtures.

---

## Wave 4 wrap-up

```bash
poetry run pytest
scripts/ui_flag_sweep.sh
poetry run python scripts/seed_dev.py     # twice; and once against a fresh DB
```

A fresh-database run matters here more than usual: this wave adds a column with
a backfill-by-derivation, and a dev DB that has been hand-edited across sessions
will not exercise it. Drop and recreate, `aerich upgrade`, seed, and confirm
every pre-existing tournament resolves to the runner it had before.

Then walk each runner's tournament through its own workflow in the browser at
both widths, and confirm the proctor board contains exactly the on-site and
manual-remote matches — no racetime ones, and nothing missing.

Suggested PR split: *"Store how a tournament is run"* (T4.1), *"Add a manually
run online tournament type"* (T4.2, T4.4), *"Let admins choose how a tournament
is run"* (T4.3).
