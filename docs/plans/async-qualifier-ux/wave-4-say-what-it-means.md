# Wave 4 — say what the numbers mean, and why you cannot start

**Read [README.md](README.md) first. Waves 1–3 must be merged.**

The two minors, and the copy work that makes the surface explicable. Nothing here
changes a rule or a formula: a score legitimately moves after a runner finishes,
and *"No pools available to run right now."* is legitimately shown for five
different reasons. Both are correct and neither is stated.

| Task | Touches | Size |
|---|---|---|
| T4.1 | why you cannot start, specifically | medium |
| T4.2 | what Score and Estimate mean, and that Score moves | medium |
| T4.3 | seed a closed qualifier so the player's board is reachable | small |
| T4.4 | docs, and retire the audit | small |

Closes **F6** and **F7**, and ends the plan.

---

## T4.1 — Why you cannot start, specifically

### The problem, precisely

`get_player_pools`
([`:440-457`](../../../application/services/async_qualifier/async_qualifier_service.py#L440))
returns `[]` when the window is shut, when the player has used every slot in
every pool, when no undrawn permalink is left in any pool, when the qualifier has
no pools at all, and when `user is None`. The page collapses four of those into
*"No pools available to run right now."* and the fifth into *"This qualifier is
not open for runs."* ([`qualifiers.py:125,136`](../../../pages/qualifiers.py#L125)).
The runner cannot tell whether to wait, ask an admin, or go home.

### The service method

```python
@dataclass(frozen=True)
class RunAvailability:
    """Whether this player can start a run, and if not, why not."""

    pools: List[AsyncQualifierPool]
    reason: RunUnavailableReason | None   # None ⇔ pools is non-empty
    message: str                          # '' when a run can be started
```

```python
    @requires_feature(FeatureFlag.ASYNC_QUALIFIERS)
    async def get_run_availability(self, user: Optional[User], qualifier_id: int) -> RunAvailability:
```

It **does not raise** for a shut window — the closed case is the answer, not an
error. That is why it is a new method rather than a change to `get_player_pools`,
which keeps its `ensure_window_open` raise for the REST client that depends on it.
Factor the per-pool eligibility loop into a private helper both call, so the
eligibility rule stays in one place.

The reasons, and the sentence each one owes the runner:

| Reason | Message |
|---|---|
| `NOT_ACTIVE` | *"This qualifier isn't accepting runs."* |
| `NOT_OPEN_YET` | *"This qualifier opens {when}."* — `format_eastern_display` |
| `CLOSED` | *"This qualifier closed {when}. The leaderboard is below."* |
| `NO_POOLS` | *"No pools have been set up yet — check back, or ask an organiser."* |
| `ALL_SLOTS_USED` | *"You've used all {n} of your runs in every pool."* |
| `PERMALINKS_EXHAUSTED` | *"You've played every seed available in the pools you have runs left in. An organiser needs to add more."* |
| `ANONYMOUS` | *"Sign in to start a run."* |

`ALL_SLOTS_USED` versus `PERMALINKS_EXHAUSTED` is the distinction the audit asked
for and the one the loop can already make: a pool contributes "slots used" when
`used >= runs_per_pool` and "no candidates" when `draw_candidates` comes back
empty with slots to spare. Report `ALL_SLOTS_USED` when every pool is in the first
state; `PERMALINKS_EXHAUSTED` when at least one is in the second. The difference
matters because only one of them is something an organiser can fix.

### The page

`_render_start` and the `else` branch that prints *"This qualifier is not open for
runs."* both become one call: render `availability.message` when `pools` is
empty, and the pool buttons when it is not. The `open_now` / `_window_open`
branch in `render` ([`:119-125`](../../../pages/qualifiers.py#L119)) collapses
into it — `_window_open` stays only for T3.4's reattempt gate.

While the runner *can* still start, show what they have left, per pool:

```
Standard Pool — 1 of 2 runs used
Bonus Pool — 2 of 2 runs used
```

The counts come from the same loop; return them on `RunAvailability` (a
`pools_used: dict[int, int]`, or a small per-pool record — pick one and keep the
page dumb). This is the line that would have made F7 self-answering.

### Tests

`tests/services/test_async_qualifier_service.py`, one per reason:

```python
async def test_availability_reports_not_open_yet(db)
async def test_availability_reports_closed(db)
async def test_availability_reports_all_slots_used(db)
async def test_availability_reports_permalinks_exhausted(db)   # slots left, no undrawn seeds
async def test_availability_lists_pools_when_a_run_can_be_started(db)
```

`test_availability_reports_permalinks_exhausted` is the one to write first — it
is the reason that has never been distinguishable, so it is the one most likely
to be mis-derived.

---

## T4.2 — What Score and Estimate mean, and that Score moves

### Why a score moves, stated where the score is

`review_run` calls `recompute_par_and_scores`, which re-pars the permalink from
the approved set and **rescores every approved run on it**
([`:636-640`](../../../application/services/async_qualifier/async_qualifier_service.py#L636)).
So a runner's score changes when a stranger's run is approved. That is correct —
par is a moving average of the fastest approved times — and the page never says
so.

Under the **My runs** table:

> Scores are relative to each seed's par — the average of the fastest approved
> runs on it. Approving someone else's run on a seed you played can move your
> score. 100 is par; the cap is 105.

Those numbers are `SCORE_MIN` / `SCORE_MAX` / the formula in
[`async_qualifier_scoring.py:44-49`](../../../application/services/async_qualifier/async_qualifier_scoring.py#L44).
Do not restate the formula in the copy — state the two anchors a competitor
actually reasons with (100 = par, 105 = cap).

### Estimate

`Estimate` is a column on both leaderboards and is defined on neither. From
[`build_leaderboard`](../../../application/services/async_qualifier/async_qualifier_scoring.py#L72):
`actual` scores unfilled slots as zero; `estimate` fills every slot at the
player's mean realised score, so a player who has run 2 of 6 slots is not ranked
as though they scored zero four times.

Add a caption under both leaderboards:

> **Score** is your realised total — unrun slots count zero. **Estimate**
> projects your unrun slots at your own average, so a partial entrant isn't
> understated. Ranking is by Score.

and add a `Slots` column (`slots_filled/slots_total`) to the **player's**
leaderboard, which the admin one already has
([`admin_qualifiers.py:471`](../../../pages/admin_tabs/admin_qualifiers.py#L471))
— without it, "unrun slots" names something the player cannot see.

Prefer the caption to a header tooltip: a tooltip is invisible on a phone, which
is where the mobile grid renders `Estimate` as a labelled line with no
explanation at all.

### Tests

Copy, so no unit test earns its keep. Verify by screenshot at both widths (which
the definition of done requires anyway), and check the captions do not push the
mobile card past a screenful — if they do, cut words, not the explanation.

---

## T4.3 — Seed a closed qualifier

The dev seed creates exactly one qualifier, active with `closes_at = now + 7
days` ([`seed_online.py:334-348`](../../../scripts/seed_online.py#L334)). Under
the information lockdown, that means **a player can never see a leaderboard in
dev** — `get_leaderboard` raises `PermissionError` for every non-admin, so the
board T4.2 is documenting is unreachable to the role it is written for.

Add a second qualifier: *"Dev Async Qualifier (Closed)"*, `closes_at` in the past,
one pool, two permalinks, and three approved scored runs across `player_two`,
`player_three` and `player_four` with different slot counts so `actual` and
`estimate` visibly differ and the `Slots` column is not all `1/1`.

That fixture pays for itself three ways: the player leaderboard becomes
reviewable, T4.1's `CLOSED` message becomes reachable, and the lockdown stays
demonstrable on the *open* qualifier next to it.

Idempotent and tenant-scoped like its neighbour. Extend the `_seed_qualifiers`
docstring — it currently describes the single-qualifier fixture and would
otherwise be wrong.

---

## T4.4 — Docs, and retire the audit

**Docs.**

- [`docs/features/online-tournaments.md`](../../features/online-tournaments.md) —
  the scoring explanation (par, 100/105, why a score moves) and the availability
  reasons as a table. This is the doc that has to survive the deletion of
  everything else here.
- [`docs/reference/services.md`](../../reference/services.md) —
  `get_run_availability`, and that `get_player_pools` is retained for REST.
- [`docs/development.md`](../../development.md) — the second qualifier fixture, if
  it enumerates seed data.

**Then retire the plan and the audit**, per the README's closing section and
[`docs/README.md`](../../README.md)'s convention that design records are not kept
after they ship:

1. delete `docs/reviews/async-qualifier-run-ux.md` and this whole plan directory;
2. remove the audit's row from the table in
   [`docs/reviews/README.md`](../../reviews/README.md) and both rows from "Work in
   flight" in `docs/README.md`;
3. fix the three cross-cutting-theme bullets in `docs/reviews/README.md` that
   this plan invalidates — *"Capabilities nobody wired are invisible"* (drop
   `reattempt_run` and `review_run`'s `note`; the bracket entries stay),
   *"Confirmation is spent on the reversible actions"* (drop the qualifier
   forfeit), and the "Shipped and deleted" line, which gains this audit;
4. leave `docs/reviews/README.md`'s **Method** section alone — it is the standing
   guide for the next audit, not a record of this one.

Do **not** delete the audit before its last finding is merged: it is the only
place the measured "before" numbers exist, and a half-shipped plan whose evidence
has been deleted cannot be finished by anyone else.

---

## Wave 4 wrap-up

```bash
poetry run pytest
poetry run python scripts/seed_dev.py     # twice
scripts/ui_flag_sweep.sh
grep -rn "async-qualifier-run-ux" docs/
```

That last grep must come back empty — a dangling link to a deleted audit is the
usual way this cleanup half-happens.

Then, as `player_two` at both widths:

1. On the open qualifier: the per-pool "1 of 2 runs used" lines are present and
   correct; spend every slot in every pool and confirm the message becomes
   *"You've used all 2 of your runs in every pool."*, not the old generic one.
2. On the closed qualifier: the `CLOSED` message, the leaderboard visible, and
   the Score/Estimate/Slots caption legible on a phone.
3. As `staff_user`, the admin leaderboard carries the same caption — the two
   surfaces must not explain the same column differently.

Commit as *"Explain qualifier scoring, and say why a run cannot be started"*.

With this merged, every finding in the async-qualifier audit is closed. Say so in
the PR body, listing F1–F7 against the waves that closed them — that list is what
makes deleting the audit safe.
