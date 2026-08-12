# Code-quality drift — audit

**Date:** 2026-08-12 · **Audited commit:** `ce733111fbb487d80c43c4e1bd3667a52a7b68a0`
· **Status:** report only, nothing here is fixed.

**Scope:** the whole tree — `application/` (257 files, 46.5k lines), `api/` (79),
`pages/` (98), `theme/` (75), `mcpserver/` (24), `discordbot/` (9),
`racetimebot/` (6), `models/` (22), `tests/` (304 files, 64.2k lines),
`scripts/` (32) and `.claude/scripts/` (29 hooks). The question asked was not
"does it work" but "has it drifted": one rule implemented twice and now
disagreeing with itself, a convention that holds in nine places and lapses in the
tenth, and the correctness bugs those gaps expose.

**Delta window.** This is a shallow clone: 319 commits, 2026-07-27 → 2026-08-12,
881 files, +90,180/−20,021. `.git/shallow` holds **16** grafted boundaries, so a
finding is labelled **[new]** when `git blame` lands on a real commit in that
range and **[pre-existing]** when it lands on any graft (`a38c86d` is the one most
lines hit). The first framing of this audit named a single boundary; three
reviewers independently corrected it, and the corrected method is what the labels
below use.

**Method.** Five parallel section reviewers (application layer, API + MCP,
presentation, tests, engineering practice), then an adversarial reconciliation
pass that re-ran every count and re-read every cited line against HEAD. Findings
whose severity was contested went to a separate re-checker briefed to defend the
original rating. Empirical probes ran against the real services through the test
harness and were deleted afterwards; no test file in the tree was modified.

**Headline.** The mechanical invariants are in excellent shape and the reason is
`.claude/scripts/` — 22 checks over 1,088 files report clean with two baselined
hits, every NiceGUI anti-pattern is at zero, `api/` and `mcpserver/` do not touch
`application.repositories` once in 112 files, and no production `.create()` on
any of the 61 tenant-scoped models omits its tenant stamp. What has drifted is
everything the hooks do not watch. Two findings stand out. The whole-tree
guardrail sweep **cannot fire `check_dry_regressions` at all** — it reports clean
over 56 hits the check itself names as forbidden. And the manual live-race record
shipped in this very commit **erases the "these racers matched nobody" to-do**
whenever it runs, while the card above the button tells the admin to do exactly
that.

---

## Reconciliation summary

| | Count |
|---|---|
| Findings raised by the five reviewers | 63 |
| **Confirmed** at the stated severity, citation re-verified | 55 |
| **Corrected** in place (severity or consequence changed) — each carries a `_[Reconciled: …]_` note | 6 |
| **Retracted** | 2 |
| **Added during reconciliation** (T1.2, T2.6, T5.18) | 3 |
| Entries below (several reviewer findings bundled two issues and were split) | 70 |

Retracted: a claimed unscoped read in `discordbot/_tenant.py:16,27` is the
documented cross-tenant discovery path a DM press requires (a Discord DM carries
no guild, so the entity's own row is how its tenant is found — the module
docstring says so); and a claimed `write_log` + `event_bus.publish` pair in
`VolunteerScheduleService.assign` is correctly split, because the audit is
unconditional and the publish is not.

Corrected: the qualifier's mishandled racetime finisher does not land on the
board as a zero, it **disappears from the board entirely** (probed); the
`sanitize_return_path` divergence is not a reachable open redirect; the volunteer
hours disagreement is a decision-affecting reporting split rather than data loss;
`POST /volunteers/shifts/{id}/assignments` is worse than the medium it was filed
at; and two counts moved by one or two (`env_flag` bypasses, DRY-hit file union).

Two numbers I could not reproduce from a reviewer's own command are labelled
*reviewer-measured* where they appear.

Both contested downgrades went to a re-checker briefed to defend the original
rating. Both downgrades survived, each with its reasoning corrected rather than
merely accepted — and the defence turned up two findings nobody had raised
(T2.6, T5.18), which is the case for running it.

---

## Executive summary

| # | Theme | Worst severity | Age | Where |
|---|---|---|---|---|
| T1 | The drift guards have holes in the places drift collects | critical | pre-existing | `scripts/guardrails.py`, `.claude/scripts/check_dry_regressions.py`, `check_feature_flag_gating.py`, `guardrail_baseline.json` |
| T2 | Silent partial success — an incomplete result reported as a complete one | critical | new | `async_qualifier_live_race_service.py`, `admin_qualifiers/live_races.py`, `mcpserver/tools/competition.py` |
| T3 | One upstream fact, two capture paths, diverged | high | mixed | `race_room_service.py` vs `async_qualifier_live_race_service.py`, `_bracket/scheduling.py` |
| T4 | A shared primitive existed and a second copy was written anyway | high | mixed | `volunteer_export_service.py`, `match_reschedule_service.py`, `theme/notify.py` callers, `match_station_draw.py` |
| T5 | Gates that are not gates | high | mixed | `race_room_service.py`, `api/routers/volunteers.py`, `api/_match_view.py`, `user_service.py` |
| T6 | What a green suite does not prove | critical | mixed | `tests/conftest.py`, `tests/factories.py`, worker modules, `pyproject.toml` |
| T7 | Config, dead code and doc drift | high | mixed | `frontend.py`, `application/utils/environment.py`, `docs/reference/data-model.md` |

---

## The five extractions that remove the most debt

Each is mechanical or nearly so, and each deletes a class rather than an instance.

1. **Repair the sweep's payload for `check_dry_regressions`** (T1.1). One
   function in `scripts/guardrails.py`. It turns 56 currently-invisible
   violations into a baseline that can only shrink, and it is the difference
   between a whole-tree sweep that certifies the tree and one that certifies
   nothing.
2. **`make_staff()` in `tests/factories.py`, and collapse the 35 copies onto it**
   (T6.3). The single largest duplication in the repo, and 34 of the 35 copies
   build a user no community can see.
3. **`_dm_opt_ok` becomes the only way to decide whether a DM may be sent** (T4.2)
   — ideally inside `DiscordService.send_dm`. Removes 11 hand-rolled copies and
   closes three paths that have no copy at all.
4. **`Page[T]` + a `PageParams` dependency in `api/`** (T4.6). Two identical
   envelopes, six caps and five ceilings become one, and the two unbounded reads
   in T5.5 get their limit for free.
5. **`notify_error` everywhere** (T4.4). 61 hand-rolled sites, 30 of which paint
   an authorization refusal amber, and a hook mirroring `check_table_prefs.py`
   stops it re-growing.

---

## T1 — The drift guards have holes in the places drift collects

### T1.1 The whole-tree sweep cannot fire `check_dry_regressions`, and reports clean over 56 hits — **critical** · [pre-existing]

`scripts/guardrails.py:184-188` shapes every replay as an `Edit` whose
`old_string` is the base revision:

```python
return run_hook(name, {
    "tool_name": "Edit",
    "tool_input": {
        "file_path": str(ROOT / path),
        "old_string": base_content(path, base),
```

`.claude/scripts/check_dry_regressions.py:182-183` then bails:

```python
if not old_string or old_string not in old:
    return None  # the Edit itself will fail; nothing to judge
```

Neither mode can fire. On `--all` there is no base, so `old_string` is `''` and
the check exits 0 on every file. On `--changed` the base content of a *modified*
file is not a substring of the current file, so it exits 0 there too; for an
*unmodified* file `old == old_string`, the synthesized "new" equals the current
content, and net-new is zero. `check_dry_regressions` is not in
`EXCLUDED_CHECKS` (`guardrails.py:92-101`) — the runner believes it is enforcing
it, and `tests/test_guardrail_ci_parity.py` only asserts that every hook appears
in one of the lists, not that it can produce a hit.

Measured by importing the hook and replaying its own eight live rules over the
tree:

```
30  test-factory-redefinition       8  router-preload-404
 6  service-not-found-valueerror    6  test-fixture-redefinition
 3  audit-publish-pair              1  env-truthiness-literal
 1  repo-update-loop                1  local-audit-emit-wrapper
TOTAL 56 across 52 files
```

against `python scripts/guardrails.py --all` → `1088 file(s), 22 check(s) —
clean (2 baselined hit(s) unchanged)`. Three of the 56 are documented as
deliberate (`docs/current-state.md:33-41`). `.github/workflows/guardrail-sweep.yml:4-8`
exists specifically because "a violation can enter the tree by a route no diff
covers"; for the one check that is only meaningful as a sweep, it sweeps nothing.

**Fix:** send the check a payload it can judge on a sweep (`tool_name: "Write"`
with `old` forced empty), then baseline the 53 undocumented hits.

### T1.2 …and the rule's factory allowlist misses the copies that actually exist — **high** · [pre-existing]

Found during reconciliation; neither reviewer had it. The
`test-factory-redefinition` rule guards three names:

```
def\s+(?:utc|make_user|_user)\s*\(
```

Definition counts in `tests/`, by name:

| `_staff` | `make_user` | `_tournament` | `_match` | `_user` | `_player` | `utc` |
|---|---|---|---|---|---|---|
| **35** | **22** | 10 | 10 | 9 | 7 | 1 |

`utc` — one definition, the canonical one — is guarded. `_staff`, at 35 copies
the most duplicated helper in the repo, is not. So even a repaired sweep (T1.1)
would leave the largest copy set unseen.

**Fix:** extend the alternation to `_staff|_racer|_player|_tournament|_match`
once `tests/factories.py` has the shared factories to point at.

### T1.3 `guardrail_baseline.json` is boolean per file, so the 1,500-line hard cap is off for two files — **high** · [pre-existing]

Each hook exits once per file, so `guardrails.py:250` can record at most `1` hit
per `(check, path)`. `check_file_length` exits 2 for **both** tiers
(`.claude/scripts/check_file_length.py:48` `HARD_LIMIT = 1500`, `:58`
`SOFT_LIMIT = 800`), so one baselined hit exempts the file from the hard cap too:

```json
"check_file_length": { "scripts/seed_dev.py": 1,
                       "tests/services/test_match_schedule_coverage.py": 1 }
```

`scripts/seed_dev.py` is 875 lines today and has been over budget for the whole
window; commit `aafae4b` is titled "…split seed_dev.py under budget".

**Fix:** report the overage as the hit count (`lines - SOFT_LIMIT`, or 2 hits past
the hard cap) so a baselined file can only shrink.

### T1.4 `check_feature_flag_gating` skips a class whose only guard is inline — **high** · [pre-existing]

`.claude/scripts/check_feature_flag_gating.py:204-210` builds `decorated` from
decorator source, then:

```python
if not decorated:
    continue
```

A class with zero `@requires_feature` decorators is classified as an ungated
internal collaborator and skipped wholesale — which is exactly the shape of a
feature that is UI-gated only. See T5.1 for the live instance; the hook exits 0
on that file.

**Fix:** when a `FeatureFlagSpec` names a module in `service_modules`, require at
least one guard in it rather than treating zero as "not applicable".

### T1.5 CLAUDE.md sanctions the router shape the DRY hook forbids, naming the same file — **high** · [pre-existing]

CLAUDE.md: "the sanctioned shape is `Tournament.get_or_none(...)` in
`api/routers/tournament_actions.py`". The hook
(`check_dry_regressions.py:74-81`) blocks `def _load\w*_or_404` in any
`api/routers/` file, and `api/routers/tournament_actions.py:24` is
`_load_tournament_or_404`. Eight routers carry the helper. The next author
reading CLAUDE.md adds a ninth; the next author reading the hook deletes all
eight.

**Fix:** pick one authority — drop the rule, or amend the sentence to name the
service-side `require_found` as sanctioned.

### T1.6 The leak ratchet matches prose, not code — **medium** · [pre-existing]

`tests/tenancy/test_leak_test_coverage.py:55-56` regexes the model name against
the concatenated source of every `*isolation*.py`, so a **docstring mention**
satisfies it. `RacetimeBotTenant`, `AuditLog` and `TelemetryEvent` pass on a
module docstring alone. All three are genuinely covered today, so this is
latent — but the next scoped model can satisfy the ratchet with a comment, and
`test_backlog_is_current` would then refuse to record it as debt.

**Fix:** strip docstrings and comments before the regex, or require the name in
an `await X.create(` / `scoped(X.` position.

### T1.7 Two migrations claim sequence `61`, and nothing checks — **low** · [new]

`61_20260803060000_preset_owns_randomizer.py` and
`61_20260803082215_add_stage_reminder_fields.py`. Aerich orders by full filename
so application is deterministic and the `migrations` job passes, but "migration
61" is now ambiguous in every doc that addresses migrations by number.
`enforce_migration_safety.py` and `check_migration_drift.py` have no
prefix-uniqueness assertion.

**Fix:** assert prefix uniqueness in `enforce_migration_safety.py`; renaming the
existing pair is not worth the aerich bookkeeping risk.

---

## T2 — Silent partial success

The unifying failure: the code completes part of a job, reports the part it did,
and destroys or omits the evidence of the part it did not.

### T2.1 A manual live-race record erases the unmatched-handle to-do, and the UI tells the admin to do it — **critical** · [new, `ce73311`]

`application/services/async_qualifier/async_qualifier_live_race_service.py:329`
passes an empty list, and `:426` treats empty as "nobody is unmatched":

```python
return await self._capture(
    live_race, resolved, actor=actor, unmatched=[], manual=True,
)
...
    # Cleared when nobody is left unmatched, so the card's to-do disappears
    # once the accounts are linked and the race is recorded again.
    unmatched_handles=unmatched or None,
```

The comment is true of the racetime path, which recomputes the list from the
entrants. It is false of the manual path, which always passes `[]`. And
`pages/admin_tabs/admin_qualifiers/live_races.py:97-105` routes the admin
straight into it:

```python
ui.label('Their results were not recorded. Link the account on '
         'Admin → Users, then record this race again.')
```

Probed against the real services:

```
after racetime capture, unmatched_handles = ['Stranger']
after manual record,    unmatched_handles = None
runs on the race       = 1
```

The warning vanishes, the racer still has no run, and par is now the mean of a
field the admin believes is complete — so every score in the pool is computed
from the wrong denominator. The handle survives only in the audit detail, which
is the channel wave 7's own test docstring calls "not a place anyone looks for
work".

**Fix:** carry the existing handles through the manual path, minus the racetime
ids of the users actually recorded — `unmatched=list(live_race.unmatched_handles
or [])` filtered by what was captured.

_[Fixed in `573fef2` — `_handles_still_outstanding` matches on racetime username
or account id, whichever the stored handle holds, and leaves a handle it cannot
attribute standing.]_

### T2.2 A blank racer row is dropped and the toast counts the rest as success — **medium** · [new, `ce73311`]

`pages/admin_tabs/admin_qualifiers/live_races.py:187-212`:

```python
for entry in rows:
    if not entry['person'].value:
        continue
...
ui.notify(f'Recorded {len(captured)} run(s)', color='positive')
```

Four rows filled, one racer left blank, and the answer is "Recorded 3 run(s)" in
green. The service is strict about every other input, so the page is the only
place a result goes missing. The sibling that got this right is one commit
earlier: `pages/admin_tabs/admin_qualifiers/pools.py:194-206` reports
`result.summary` per refused line and keeps the text in the box.

_[Reconciled: filed high, corrected to medium — nothing wrong is written and the
Runs tab shows what was captured. The class is the same as T2.1; the consequence
is not.]_

**Fix:** collect the skipped row positions and name them, the way
`add_permalinks_bulk`'s summary does.

_[Fixed in `573fef2` — a pure `missing_racer_message` refuses the submit and names
the rows, so the wording is testable without building the dialog.]_

### T2.3 Two MCP reads answer `null` for the field the caller asked for — **high** · [pre-existing]

`mcpserver/tools/competition.py:61,65` reads three names the dataclass does not
have:

```python
'group': getattr(group, 'name', None),
'entrant': getattr(row, 'label', None) or getattr(row, 'name', None),
```

Verified against the real types: `StandingsGroup` has `group_number` and `rows`;
`StandingsRow` has `display_name`, no `label`, no `name`. So
`get_bracket_standings` returns a standings table with every identity stripped
out. Same shape at `:176` — `getattr(q, 'active', None)` where the field is
`is_active`, so `list_async_qualifiers` reports `active: null` on every row. The
`getattr` defaults are what hide it: no `AttributeError`, nothing for
`map_service_error` to catch, and the REST peers are correct, so the two surfaces
disagree in silence.

Neither tool is executed by any test — `get_bracket_standings` and
`list_async_qualifiers` appear only in the catalogue snapshot
(`tests/mcp/test_mcp_catalogue.py:27,40`), which is why this shipped.
`docs/features/mcp-server.md:472-475` claims `test_mcp_reads.py` "calls every
read tool against seeded rows"; nothing asserts that.

**Fix:** read the real attributes without `getattr`, give the tool a typed row
model beside its `LeaderboardRow` sibling, and add
`test_every_read_tool_is_exercised` over `READ_TOOLS`.

### T2.4 `GET /webhooks/{id}/deliveries` truncates at 50 with no way to page and no signal — **medium** · [pre-existing]

`api/routers/webhooks.py:81-87` exposes neither parameter, though the service
already takes both (`webhook_service.py:217-222`, `limit=50, offset=0`). An
operator asking what happened to delivery 80 gets a silently short array.
`docs/reference/rest-api.md:181` documents no parameters, so the doc is accurate
about an endpoint that is wrong.

### T2.5 A swallowed prefetch renders a live series as unplayed — **medium** · [pre-existing]

`application/services/_bracket/scheduling.py:445-450`:

```python
try:
    return list(bracket_match.games)
except Exception:
    return []
```

Feeds `matchup_live_state` (`:373`), which backs the public bracket views. A
caller that forgets `prefetch_related('games')` gets an empty series with no log
line and no test failure.

**Fix:** catch Tortoise's specific unfetched-relation error and warn with the
`bracket_match.id`, or take the games as a parameter.

### T2.6 Login drops the query string, so every staff deep link lands on the page instead of the control — **high** · [pre-existing]

Found by the re-check pass. `middleware/auth.py:420` stores the path and nothing
else:

```python
app.storage.user['referrer_path'] = f'{root_path}{path}'   # path = request.url.path
```

`request.url.path` excludes the query string, and every staff deep link is built
*with* one — `admin_url(section, **params)` appends `?…`
(`application/utils/app_links.py:48-50`), so
`admin_qualifier_queue_url` is `/admin/qualifiers?qualifier=7&tab=queue`,
`admin_reschedule_request_url` carries `?reschedule_request=`, and the schedule
link carries `?match_id=`. `/admin/{section}` and `/volunteer/{section}` are both
protected routes, so a recipient who is signed out — the normal case for a DM read
on a phone — bounces to `/login` and returns to the bare board with the parameter
gone.

That is the failure CLAUDE.md's calls-to-action section names first: "Linking a
page rather than the control." The docstring of
`notification_links.admin_qualifier_queue` spells out the cost it is trying to
avoid ("three steps between a 'runs are waiting' DM and the runs") and the login
bounce reinstates all three. Player links escape only by accident: `/home/*` is
registered with a bare `ui.page` (`pages/home.py:182-184`), so it never joins
`protected_routes` and never bounces.

**Fix:** store `request.url.path` plus `request.url.query` when present — and
because the stored value then contains user-supplied text, this is the change that
makes T5.4 load-bearing, so do both together.

---

## T3 — One upstream fact, two capture paths, diverged

### T3.1 A racetime `DONE` entrant with no finish time is scored by one path and filtered by the other — **high** · [new, `ce73311`]

`application/services/race_room_service.py:243-245` defends the None:

```python
finishers = [
    e for e in entrants
    if e.status == EntrantStatus.DONE and e.finish_time is not None
]
```

`async_qualifier_live_race_service.py:274-275` does not — it takes
`entrant.finish_time` for any DONE entrant. Probed:

```
user=good  status=FINISHED review=APPROVED elapsed=3600 score=100.0
user=weird status=FINISHED review=APPROVED elapsed=None score=None
board rows: [good]
```

A runner racetime reported as finished is written approved with no time, scores
`None`, and then **does not appear on the leaderboard at all**. With other runs
on the board the slot counts as a realised zero instead. Nothing flags it: no
reviewer queue entry, no `unmatched_handles`, no audit note.
`application/utils/racetime_entrants.py:5-9` documents the two paths as sharing
an idiom; they share only `unmatched_handle`.

_[Reconciled: filed as "lands on the board as a hard zero", corrected — the probe
shows the runner is absent from the board entirely when this is their only run.]_

**Fix:** put the finisher predicate in `application/utils/racetime_entrants.py`
and use it in both paths; a DONE entrant with no time belongs on the
staff-reconcile route, not in an approved row.

_[Fixed in `573fef2` — `is_scored_finish` is the shared predicate both paths now
call, and the entrant goes on the to-do the record dialog resolves.]_

### T3.2 The bracket schedulability guard is duplicated, and the copy the comment warns about is the one missing the check — **high** · [pre-existing]

`_bracket/scheduling.py:129-143` has four guards, and the third explains itself:

```python
if bracket_match.bracket.state == BracketState.CANCELLED:
    # Cancelling a stage flips the bracket's state and leaves its
    # matchups OPEN, so the matchup check above passes on a stage that
    # is terminal and cannot be advanced from. Hiding it from the
    # listings is not enough — a stale dialog, the REST route and the
    # admin's link picker all arrive here too.
    raise ValueError("This stage was cancelled — …")
```

`link_match_to_bracket_match` (`:256-261`) repeats the other three verbatim and
omits this one. `grep -n CANCELLED` finds it once in the file. So the admin link
picker — the caller the comment names — can attach a live `Match` to a matchup on
a cancelled stage, and `list_linkable_matches` (`:201-212`) filters on entrants
and free slots only, so the picker offers it.

**Fix:** extract `_require_schedulable(bracket_match)` covering all four and call
it from both entry points.

### T3.3 Three finish-time validators, three rule sets — **high** · [new]

One quantity reaches `AsyncQualifierRun` three ways:

| path | `<= 0` | `> MAX_RUN_SECONDS` | plausibility vs the measured clock |
|---|---|---|---|
| `async_qualifier_service.py:295` `submit_run` | yes | yes | yes (`classify_claim`) |
| `async_qualifier_live_race_service.py:282` `record_manual_finish` | yes | yes | no |
| `async_qualifier_live_race_service.py:242` `record_finish` | no | no | no |

The two that check disagree on wording — "Finish time is longer than a week —
check the value you entered." against "That finish time is longer than a week —
check the value" — which is the tell that they were written twice.

**Fix:** one `validate_finish_seconds()` in `async_qualifier_rules.py` beside
`classify_claim`, called by all three.

### T3.4 `_map_results` sorts two units in one slot — **medium** · [pre-existing]

`race_room_service.py:246`:

```python
finishers.sort(key=lambda e: (e.place if e.place is not None else e.finish_time))
```

`place` is 1-based, `finish_time` is seconds. When racetime reports `place` for
some entrants and not others, every place-less entrant sorts after every placed
one regardless of who was faster, and the `enumerate` fallback rank at `:249-250`
derives from that order — straight into `finish_rank` and `_publish_match_result`.

**Fix:** `key=lambda e: (e.place is None, e.place or 0, e.finish_time or 0)`.

### T3.5 A bot-driven capture failure leaves the room stale and nobody told — **medium** · [new]

`race_room_service.py:406-409` updates the room only after `record_finish`
returns, and that call raises for three reachable reasons (an entrant still
IN_PROGRESS, no permalink assigned, the qualifier flag off).
`racetimebot/handler.py:67-73` catches and logs. Race stays IN_PROGRESS, room
stays IN_PROGRESS, nothing reaches staff — and the hand-record remedy T2.1 was
built for is exactly what nobody knows to use.

**Fix:** update the room in a `finally`, and record the failure as an
operator-visible signal rather than only `logger.exception`.

---

## T4 — A shared primitive existed and a second copy was written anyway

In every case below the helper predates the copy, so this is not "we should
extract something" — it is "the extraction happened and the next author did not
find it".

### T4.1 The volunteer hours roster counts overlap once; the CSV double-counts — **high** · [new fix in one copy only]

`application/services/volunteer/volunteer_hours.py:30` `merged_hours` is
explicit: "08:00-12:00 plus 10:00-14:00 is six hours served, not eight", and it
drops zero-length and inverted windows.
`application/services/volunteer/volunteer_export_service.py:66,249` sums per
assignment with no merge and no clamp. The Hours roster
(`pages/admin_tabs/admin_volunteer_roster.py:54`) uses the first; the CSV's
"Assigned Hours" column (`theme/dialog/volunteer_export_dialog.py:39`) uses the
second. `merged_hours` is `dd288ee8` (2026-08-03), `_hours` is pre-existing — the
fix landed in one copy. It is in fact the **fourth** copy of the hours formula:
`reporting_shared.window_hours:31-35` is the shared `max(0.0, …)`-guarded
version, and `volunteer_autoschedule_service.py:265-270` is a third.

Probed end to end, one volunteer on two 4-hour shifts with the second moved into
overlap through `update_shift`:

```
ROSTER  hours=6.0   tier_cleared=None  next=8.0
EXPORT  shifts=2    assigned_hours=8.0
```

The CSV side clears the 8-hour comp tier the roster says is two hours away. A
second divergence needs **no overlap at all** and is present after every
autoschedule run: `_volunteers_sheet` (`volunteer_export_service.py:246-253`)
iterates `shift.assignments` unfiltered while the roster reads
`published_for_window` (`auto_generated=False`), and the export never clips to the
window while `merged_hours` does. One draft assignment plus one shift straddling
the window edge gives roster 8.0 against export 13.0.

_[Reconciled: filed critical, corrected to high, and the downgrade was defended.
Every consumer of a comp-tier decision reads `merged_hours` — the roster page, the
volunteer's own My Shifts (`pages/volunteer_tabs/my_shifts.py:66`) and
`GET /volunteers/hours` — and no payout or reimbursement path exists in the
volunteer services at all. The export column reaches a human-read CSV and nothing
else, so the ceiling is a coordinator misreading a column, not a wrong entitlement
issued. It stays high rather than medium because the two numbers are labelled
"Hours" and "Assigned Hours" on surfaces the same coordinator uses in one sitting.
Separately: `merged_hours`' docstring claim that "a coordinator can hand-assign
overlapping shifts" is false as written — `assign` blocks overlap and predates it.
The real route in is T5.18.]_

**Fix:** route the per-user total in the export through `merged_hours` on
`published_for_window`, clipped to the window, keeping `_hours` only for the
single-row column where one window cannot overlap itself.

### T4.2 The DM opt-out is ignored on the whole reschedule path, and hand-rolled 11 times elsewhere — **high** · [new]

`application/services/match/_match_recipients.py:12` is the named predicate:

```python
def _dm_opt_ok(user: User, *, require_opt_in: bool) -> bool:
    """Whether a user can receive a DM: has a discord_id and (if required) opts in."""
```

`match_reschedule_service.py:617,630,722` each check `discord_id` only, and
`DiscordService.send_dm` does not check the preference either — it mirrors to
web-push at `discord_service.py:221` before the Discord attempt. So a player who
turned DMs off gets both a DM and a push for every reschedule request, agreement
and decision. The opponent (`:630`) and requester (`:722`) sites are the clear
defects; the decider site (`:617`) is staff-facing, where ignoring the preference
may be deliberate and is undocumented. Eleven independent copies of the same
predicate exist elsewhere (`crew_service.py:569`,
`volunteer/volunteer_reminder.py:81`,
`volunteer/volunteer_schedule_service.py:526,559,590,671`,
`match/match_schedule_service.py:505`, `match/match_display_service.py:394`,
`match/_schedule_notifications.py:307`,
`repositories/tournament_notification_repository.py:55,67`).

**Fix:** check it inside `send_dm`, so no path can skip it.

### T4.3 A repository decides notification eligibility — **medium** · [pre-existing]

`application/repositories/tournament_notification_repository.py:53-56,65-68`
filters on `p.user.discord_id and p.user.dm_notifications`, plus a level-set rule
at `:39-46`. CLAUDE.md: repositories are pure data access. It is also copies 10
and 11 of T4.2, applied inside a query result, so a caller cannot tell whether
the opt-out has already been applied.

### T4.4 `notify_error` is bypassed 61 times, and 30 of those paint an authorization refusal amber — **medium** · [pre-existing]

Measured: `notify_error(` at **137** sites in `pages/`+`theme/`,
`ui.notify(str(e)` hand-rolled at **61**. `theme/notify.py` maps
`PermissionError` to red and everything else to amber, and upgrades a message
over 90 characters to `multi_line` with a Dismiss button and a 15s timeout. The
hand-rolled copies get neither. `pages/admin_tabs/admin_features.py` imports
`notify_error` at line 14, uses it at 25, and hand-rolls a `PermissionError` at
32 — in the same function body. `theme/tables/match_handlers.py` imports it once
and hand-rolls six times (`:46,192,220,259,351,395`), all player-facing.

**Fix:** replace every raw form, then add a hook mirroring
`check_table_prefs.py`.

### T4.5 Presentation duplicates a service rule and its exact message — **medium** · [pre-existing]

`theme/availability_editor.py:367` raises "Each availability window must end
after it starts." and catches it four lines later; the service copy at
`volunteer/volunteer_availability_service.py:45` is byte-identical and never runs
on this path.

### T4.6 Two identical page envelopes, six caps, five ceilings — **medium** · [mixed]

`AsyncQualifierRunPage` (`api/schemas/async_qualifiers.py:194-205`) and
`AuditLogPage` (`api/schemas/audit.py:16-20`) are the same four fields, and the
newer one's docstring says so. Beneath them: `MAX_ROWS = 500` declared twice
under the same name (`reschedule_requests.py:29`, `feedback.py:34`),
`MAX_LOAN_ROWS = 200`, `RUNS_PAGE_MAX = 500`, and inline `Query` ceilings of 500,
200 and 100 — none documented as deliberately different.

### T4.7 The same ten lines guard stations in two modules — **medium** · [new, one day apart]

`application/services/match/match_stations.py:43-52` and
`match_station_draw.py:85-94` are byte-identical (`diff` returns nothing),
covering both the `can_run_match` check and the racetime refusal.

### T4.8 Three copies of the 90-minute match default — **medium** · [pre-existing]

`reporting_shared.py:19 DEFAULT_MATCH_DURATION_MIN = 90`,
`crew_service.py:243 DEFAULT_MATCH_MINUTES = 90`, and
`match/match_suggestion_service.py:66 … or 90`. The comment at
`crew_service.py:242` claims parity with `MatchSuggestionService`, which has no
constant to be parity with. `reporting_shared`'s docstring exists so the Reports
and Insights dashboards "can never silently disagree"; the crew conflict dialog
and the suggestion engine sit outside that guarantee.

### T4.9 Six hand-rolled truthy-env parsers in the module that declares the canonical one — **high** · [pre-existing]

`application/utils/environment.py:10-23` defines `_TRUTHY` and `env_flag`, "the
single canonical truthy-env grammar". The same file then hand-rolls
`in ('1', 'true', 'yes', 'on')` at `:85,97,109,121,133,143` for
`TELEMETRY_ENABLED`, `RACETIME_BOT_ENABLED`, `SPEEDGAMING_SYNC_ENABLED`,
`DISCORD_EVENTS_SYNC_ENABLED`, `SERVICE_HEALTH_ENABLED` and
`SERVICE_HEALTH_ALERT_DM`, and `api/rate_limit.py:70-72` makes a seventh across
two lines. `env_flag` has 10 call sites; the hand-rolled form has 6-7 depending
on how the multi-line one is counted. The DRY hook's own message cites the
`MOCK_SPEEDGAMING=on` split-brain this caused.

### T4.10 `frontend.py` re-derives the environment name — **high** · [pre-existing]

```python
frontend.py:100   self.is_dev = os.environ.get('ENVIRONMENT', 'development') == 'development'
environment.py:28 return os.environ.get('ENVIRONMENT', 'development').strip().lower()
```

`ENVIRONMENT=Production` or a trailing space splits the two, and `frontend.py`'s
answer picks the static-asset cache policy (`:108` → `theme/assets.py:29-39`,
no-store against immutable).

**Fix:** `self.is_dev = not is_production()`.

### T4.11 The table page-size allowlist is maintained in two layers — **medium** · [pre-existing]

`table_preference_service.py:35 ALLOWED_PAGE_SIZES` against
`theme/dialog/table_preferences_dialog.py:22 PAGE_SIZE_LABELS`; same for
`ALLOWED_DENSITIES`/`DENSITY_LABELS`. Add a size to the dialog and the viewer
gets a save error; add it to the service and it is unreachable.

### T4.12 `form_dialog` is called 12 times and hand-rolled 66 — **medium** · [pre-existing]

`theme/dialog/_helpers.py:44` bundles `mobile_sheet`, `dialog_header`,
`dialog_actions` and `submit_on_enter`. The 66 hand-rolled `with ui.dialog()`
blocks each pick a subset; 43 skip `mobile_sheet` and **31 of those also carry a
fixed width with no `.dialog-card` cap**, so below Quasar's 600px breakpoint they
have no width constraint at all. The two that matter most are player-facing or
new: `pages/qualifiers.py:426` (`w-[30rem]`, the dialog that voids a run) and
`pages/admin_tabs/admin_qualifiers/live_races.py:147` (`w-[40rem]`, the widest in
the app). *[reviewer-measured: the 43/31 split.]*

### T4.13 Two hand-transcribed mobile cards, both missing the class that makes them readable — **medium** · [pre-existing]

`pages/admin_tabs/admin_volunteer_roster.py:131-179` is
`theme/tables/mobile_grid.py:146-152` retyped by hand, 48 lines of it, minus
`wiz-grid-card` — which `static/css/styles.css:1592` needs to stop Quasar's
`text-grey-7` going murky on the dark surface. It also loses
`apply_column_visibility` and the `table_key` persistence. Same story at
`pages/admin_tabs/admin_settings.py:209`, which additionally registers two
`body-cell-*` slots that its own `body` slot (`:177`) shadows, then re-types
their markup inline at `:181-190`.

### T4.14 `.wiz-grid-card` is missing from the surface rule it was added for — **low** · [pre-existing]

`static/css/styles.css:1576-1584` gives the surface, border and shadow tokens to
the four bespoke family cards. `.wiz-grid-card` appears only in the
`.text-grey-7` rule below it, so every card `enable_mobile_grid` generates — some
30 tables — falls back to Quasar's default while the four family tables are
token-driven.

### T4.15 `VolunteerAutoscheduleService` reads a scoped model unscoped and re-implements `window_hours` — **medium** · [pre-existing]

`volunteer/volunteer_autoschedule_service.py:274` filters
`VolunteerQualification` with no tenant predicate and no repository, though both
exist. Not a leak today — `position_id` is globally unique, so a foreign row
cannot match a local shift — but it is the one unscoped service read on a scoped
model in the tree, and `check_tenant_scoping.py` deliberately flags only *writes*
in service modules. `:270` `_hours` is `reporting_shared.window_hours` minus its
None-guard.

---

## T5 — Gates that are not gates

### T5.1 `RACETIME_ROOMS` is UI-gated only, and a docstring claims otherwise — **high** · [mixed]

`application/feature_flags.py:107` declares
`service_modules=('application/services/race_room_service.py',)`. That module
carries **zero** `@requires_feature`; its only flag consult is an inline
`is_enabled` inside `auto_open_if_eligible` (`:126`), which is the sanctioned
worker skip. `manual_create_room:98`, `create_room_for_match:59`,
`mark_in_progress:151`, `cancel_room:168` and `record_finish:179` enforce
nothing, and `RaceRoomLifecycle.handle_event:377` ← `racetimebot/handler.py:66`
reaches them: a community that turns racetime rooms **off** still has its matches
auto-finished, `finish_rank`/`finish_time` written, Challonge pushed and brackets
settled by the bot. CLAUDE.md is explicit that UI-only gating is not gating.

`theme/dialog/match_dialog.py:65-66` asserts an enforcement that does not exist —
"without this the dialog would offer a Create button that `RaceRoomService` then
refuses". It would not refuse. The hook misses it for the reason in T1.4.

**Fix:** `@requires_feature(FeatureFlag.RACETIME_ROOMS)` on the five public
methods; keep the inline check in `auto_open_if_eligible` and mark it exempt.

### T5.2 `POST /volunteers/shifts/{id}/assignments` reaches every account on the platform — **high** · [pre-existing]

_[Reconciled: filed medium, upgraded — this is the same class as the leak the
August security audit closed, and it writes a row and sends a DM as a side
effect.]_

`api/routers/volunteers.py:149`:

```python
target = require_found(await User.get_or_none(id=payload.user_id), "User")
assignment, warnings = await service.assign(actor, shift, target)
```

`api/_helpers.py:11-17` states the rule this breaks and names the consequence
("picking the wrong one is a cross-community leak").
`VolunteerScheduleService.assign` checks `can_manage_volunteers(actor)` and
overlap, never membership. The response carries the name —
`AssignResponse.assignment.user_name` ← `user.preferred_name` at
`api/routers/volunteers.py:51` — and the refusal messages leak it too
("{preferred_name} is already on this shift."). So one community's volunteer
coordinator can count upward through user ids, read the preferred name of every
account on the platform, and each probe creates a real assignment and DMs a
stranger.

**Fix:** `await load_community_user_or_404(payload.user_id, actor)`.

### T5.3 `manage_tournament_enrollments` has no permission check; the router's copy is the only gate — **medium** · [pre-existing]

`application/services/user_service.py:446` gates nothing, so
`api/routers/users.py:146-147` is load-bearing — while the same hand-rolled
self-or-staff check two routes away at `:77-78` is redundant, because
`update_user_profile` does gate itself. Nothing marks which is which, and a third
copy lives at `mcpserver/tools/people.py:73-74` with different refusal wording.

**Fix:** a `require_self_or_staff(user_id)` dependency, and push the missing gate
into the service so the router copy becomes redundant like its neighbour.

### T5.4 `sanitize_return_path` accepts what `safe_next` rejects — **medium** · [pre-existing]

`application/utils/tenant_urls.py` ships two validators.
`safe_next:33` rejects `//host`, backslashes and control characters;
`sanitize_return_path:120` checks only the tenant prefix and the auth-route list,
and skips the prefix test entirely when `root_path` is `''`:

```
sanitize_return_path('', '//evil.com') -> '//evil.com'
safe_next('//evil.com')                -> '/'
```

`sanitize_return_path('', 'https://evil.com')` returns it verbatim too.

_[Reconciled: filed high as an open redirect, corrected to medium — not reachable
today, and the downgrade was defended rather than accepted. The re-check
enumerated `protected_routes` at runtime: nine entries, every one led by a
**literal** segment (`/admin`, `/admin/{section}`, `/equipment/qr-labels`,
`/equipment/{asset_id}`, `/oauth/mcp/consent`, `/qualifiers`,
`/qualifiers/{qualifier_id}`, `/volunteer`, `/volunteer/{section}`), and
`root_path` is only ever `''` or `/t/<slug>` with `slug` matching
`[a-z0-9][a-z0-9-]*`. Off-origin navigation needs `/` or `\` in position 2, so
`middleware/auth.py:420` cannot construct one for any request. The permissive
`[^/]+` does admit `/admin/\evil.com` and `/admin/..\..\evil.com`, but both
normalize same-origin. The sink is `window.open(prefix + path, "_self")` — an
assignment, not interpolated JS. And `sanitize_return_path` has exactly one caller
in the tree.]_

It stays at medium rather than low for two reasons the re-check established. One
route registration flips it live: a protected route led by a path parameter makes
`/\evil.com` a storable referrer on the bare platform host, and `_sanitized_return('')`
hands it to `window.open` with no other change. And T2.6's fix — storing the query
string — is exactly the change that starts feeding this validator user-supplied
text.

**Fix:** make `sanitize_return_path` call `safe_next` first, so the tenant-prefix
test narrows one rejection set rather than replacing it.

### T5.5 Two unbounded list reads survive the fix that bounded the runs endpoint — **high** · [pre-existing]

`872055d` bounded `GET /{qualifier_id}/runs` after a 500-player qualifier
answered it with a 1.66 MB body. Its nearest sibling reads the same table for the
same qualifier and was left alone —
`api/routers/async_qualifiers.py:118-124` `review-queue`, whose repository query
(`async_qualifier_repository.py:250-260`) has no `.limit()` and four prefetches
including `review_notes__author`, so it is heavier per row than the endpoint that
got paginated. `GET /speedgaming/links/{id}/episodes` is the second
(`speedgaming_episode_repository.py:28-31`), and its MCP twin has no cap either,
where an unbounded list costs the caller's context.

### T5.6 `load_match_response` is unscoped and the safer copy lives on the other surface — **medium** · [pre-existing]

`api/_match_view.py:36` filters on the id alone, and all 12 callers in
`api/routers/match_actions.py` hand it a raw path param. Not exploitable today —
each preceding service call has already refused a foreign id — but the guarantee
lives entirely in callers, and the MCP side noticed and wrote its own scoped
wrapper (`mcpserver/tools/match_writes.py:70-80`), so the shared helper is now
the less safe path. It also returns `Optional[MatchResponse]` into a
`response_model=MatchResponse`, which is a 500 rather than a 404 if it is ever
`None`. Note that `check_tenant_scoping.py` inspects repository and service
modules only, so nothing watches `api/`.

### T5.7 A refused feature toggle leaves the switch showing the new position — **high** · [pre-existing]

`pages/admin_tabs/admin_features.py:21-27` notifies and returns; the switch keeps
the value the service refused. `set_tenant_enabled` raises `PermissionError` from
`_ensure_staff` and `ValueError` when a super-admin withdrew availability while
the page was open — both reachable on a page an admin leaves open. Same at
`pages/platform.py:768-777`. The honest sibling reverts first
(`theme/dialog/match_dialog_base.py:336-337`), and a third strategy redraws from
the database (`admin_system_config.py:140-146`). Three approaches to one problem,
and the two on the surface whose whole job is reporting which subsystems are live
are the dishonest ones.

### T5.8 Twelve destructive admin actions with no confirmation, beside 26 that confirm — **high** · [mixed]

`pages/admin_tabs/admin_users.py:23-27` wires a Remove button straight to
`TenantMembershipService().remove_member` (`:176-189`). Removing a person from a
community takes one click; deleting a controller opens a `ConfirmationDialog`
naming the asset (`admin_equipment.py:201-219`). The others:
`admin_qualifiers/pools.py:141,264` (a pool delete cascades to its permalinks and
captured runs), `admin_qualifiers/live_races.py:231`,
`admin_qualifiers/page.py:272,285`, `admin_qualifiers/reviewers.py:98`,
`admin_webhooks.py:199`, `admin_racetime.py:92`, `admin_speedgaming.py:108`,
`admin_presets.py:87`, `admin_discord_roles.py:193`, `platform.py:631,742`. The
same subsystem asks a *player* to confirm voiding their own run
(`pages/qualifiers.py:304`).

**Fix:** route each through `ConfirmationDialog`, with `require_phrase=` for the
two cascading deletes.

### T5.9 `apply_link` unlinks then links with no transaction — **high** · [pre-existing]

`theme/dialog/_match_bracket_link.py:204-209` calls `unlink_match` then
`link_match_to_bracket_match`, and the second raises for six distinct reasons
(`_bracket/scheduling.py:256-286`). The wrapping handler shows a toast, but the
unlink has already committed, so the match is attached to nothing while the toast
reads like nothing happened.

**Fix:** one service method under `in_transaction()`.

### T5.10 Multi-row captures write outside a transaction in the two places that most need one — **medium** · [mixed]

`async_qualifier_draw.recompute_par_and_scores:113-131` documents the hazard and
wraps itself; its caller does not.
`async_qualifier_live_race_service._capture:371-428` loops N run writes,
recomputes par, flips the race to FINISHED and clears `unmatched_handles`
unwrapped — a failure at run 7 of 12 leaves five approved runs, a par computed
from a partial field, and a race still reading IN_PROGRESS. Same shape at
`race_room_service.record_finish:194-204`. `in_transaction` is used at 10 sites,
so this is established convention, not a new dependency.

### T5.11 Crew conflict detection misses long overlapping matches, and the comment claims otherwise — **medium** · [pre-existing]

`crew_service.py:262-273` widens the query window by **this** match's duration;
the per-pair overlap test at `:280-284` uses **the other** match's. A 180-minute
match starting 90 minutes earlier genuinely overlaps and would pass the pair
test, but `commitments_for_user` (`match_repository.py:405-406`,
`scheduled_at__gte=start`) never returns it. The comment above the call says the
window is "widened both ways so a match starting shortly *before* this one, and
still running, is caught". A coordinator approves crew off an empty conflict list.

### T5.12 "Record results" is offered on a race the service will refuse — **medium** · [new, `ce73311`]

`admin_qualifiers/live_races.py:85-88` gates the button on `!= 'cancelled'` only.
`_capture` refuses outright when the race has no permalink
(`async_qualifier_live_race_service.py:347-353`), and `_open_live_race_dialog`
deliberately offers "(assign later)", so a permalink-less race is a normal state.
The admin types every racer and every finish time, presses Record, and gets a
refusal. `lr.permalink_id` is a loaded column, so the gate is knowable at render
time — as the `Open room` button one line above demonstrates.

_[Fixed in `573fef2`. Gating the button was half of it: the refusal tells the admin
to assign a permalink, and **nothing anywhere could** — no page control, no REST
route, so "(assign later)" had no later. Adds `assign_permalink` (refused for
another pool's permalink, and once runs exist, since par is per permalink), a Set
permalink control in that state, and the REST peer.]_

### T5.13 Authorization refusals typed as `ValueError`, and "not found" too — **high** · [mixed]

`api/dependencies.py:222-238` maps `PermissionError` to 403, `NotFoundError` to
404 and `ValueError` to 400, and `require_found` is used at 130 sites. Six
stragglers raise `ValueError("… not found")`
(`triforce_text_service.py:65,138,160`, `tournament_service.py:75,98`,
`seedgen_service.py:297`) — and "Preset not found" is raised as a `NotFoundError`
two files over (`async_qualifier_pools.py:105,140`), so the same words come back
as two status codes. Three more are outright identity refusals typed as
`ValueError` (`triforce_text_service.py:143,165`,
`match/match_stream_volunteer_service.py:42`, the last **[new]**), telling a
client its request was malformed when its identity was refused. The peer rule is
one file over: `_bracket/scheduling.py:152` raises `PermissionError` for the
identical "not one of this match's players" case.

### T5.14 Two deep-link params go quiet where their siblings speak up — **medium** · [pre-existing]

`pages/home_tabs/player.py` instruments `?schedule=` and `?reschedule=` carefully
(`:38-67`), then returns before `_report_stale_deep_link(deep_link)` at `:254`
when `FeatureFlag.BRACKETS` is off — so a DM button sent while the flag was live
lands on a page with no card and no message. At `:423` a stale `?match=` id
filters the board to zero rows with only the generic chip to explain it.

### T5.15 Editing a qualifier never prefills its window, and the caption is false in edit mode — **high** · [pre-existing]

`admin_qualifiers/page.py:307-331`. Every other field prefills from `existing`;
the four window inputs do not, and `clear_window` is never passed. So an admin
editing a live qualifier cannot see the window they are editing (it is printed
one card away at `:275`), blanking a date preserves the stored value rather than
clearing it (`async_qualifier_service.py:189-190`), and there is no route to an
open-ended window from the UI at all. Three sibling dialogs already prefill with
`datetime_to_local_input` / `format_local_date`.

### T5.16 `MatchResponse` omits three fields, so three write endpoints answer with the pre-call body — **high** · [pre-existing]

`api/schemas/matches.py:86-88` carries `scheduled_at`, `seated_at`,
`finished_at`. `models/match.py:18,20,22` also has `started_at`, `confirmed_at`
and `is_stream_candidate`, and none appears in any response schema. So
`POST /matches/{id}/start`, `/confirm` and `/stream-candidate` each answer 200
with a body identical to before the call, `is_stream_candidate` is accepted on
create and is write-only forever, and the three MCP write tools inherit it.
`docs/reference/rest-api.md:75` claims the response carries "the lifecycle
timestamps".

### T5.17 The event window is derived on the viewer's clock, then re-anchored to the tenant's — **medium** · [mixed]

`volunteer_hours.py:160-172` is emphatic that the bounds belong to the community
("an event day is a property of the venue, not of whoever is reading the page")
and applies `TimezoneService.tenant_timezone_name()`. The dates it re-anchors
come from `system_config_service.py:128-136`, which derives them with bare
`to_local(...)` and `today_local()` — the request viewer's clock. With
`KEY_EVENT_START_DATE`/`KEY_EVENT_END_DATE` unset (the documented fallback), a
volunteer in Tokyo and a coordinator in New York get different window boundaries
and therefore different totals against the same comp tier. Eight callers share
the function.

### T5.18 Moving a shift creates the overlap `assign` refuses to create — **high** · [pre-existing]

Found by the re-check pass, and it is what makes T4.1 reachable.
`VolunteerScheduleService.assign:267-273` refuses to place a volunteer on a shift
overlapping one they already hold. `update_shift:178-202` validates only
`ends > starts` and `slots_needed >= 1` — no overlap re-check — while explicitly
handling the moved-shift case (`moved` is computed at `:190` and drives
`_reask_moved_shift`). So a coordinator who moves a shift onto one of its own
assignees' other shifts writes a state the service refuses to accept directly,
and nothing says so. Probed: `assign` refused the overlap, `update_shift` then
created it.

**Fix:** run the same `overlapping_for_user` check over the shift's existing
assignees inside `update_shift`, raising or returning it as a warning the way
`assign` returns its soft warnings.

---

## T6 — What a green suite does not prove

5,613 tests pass in 27.8s at 93% line coverage, and the harness design is
genuinely good (see Positives). These are the holes.

### T6.1 The test harness stamps the tenant that production code must stamp itself — **medium** · [pre-existing]

`tests/conftest.py:354-367` monkeypatches `create` on all 61 tenant-scoped models
to fill in `tenant_id=require_tenant_id()` when the caller omits it. Convenient,
documented, and it means a production write that forgets the stamp passes under
test — `check_tenant_scoping.py`'s docstring records that this is exactly how the
enrolment write in `UserService` shipped broken. I checked the current state and
it is clean: **0** of the `.create()` calls on scoped models across
`application/`, `api/`, `pages/`, `theme/`, `mcpserver/`, `discordbot/` and
`scripts/` omit a tenant kwarg. So the hook is holding, and the residual risk is
the shapes it deliberately misses (`bulk_create`, bare `obj.save()`, queries
outside a repository module).

**Fix:** promote the check I ran into a ratchet test, so the whole tree is
verified rather than the changed files.

### T6.2 The newest write endpoint has no REST test, and REST has no route ratchet — **critical** · [new, `ce73311`]

`POST /api/async-qualifiers/live-races/{id}/record`
(`api/routers/async_qualifier_live_races.py:92-111`) is referenced by no test —
`grep -rn "live-races.*record" tests/` returns nothing, and coverage shows lines
106-107, the endpoint body, as the router's only uncovered lines. Every sibling
write in `tests/api/test_async_qualifier_live_races.py` has a `_missing_is_404`
test and the module has a `TestTenantIsolation` class; `/record` has neither. Drop
`Depends(require_write_actor)` and a read-only token rewrites scored results;
drop `_load_live_race_or_404` and tenant A records into tenant B's race. Both
stay green. MCP has a catalogue ratchet for exactly this
(`tests/mcp/test_mcp_catalogue.py:19`); `api.router` has none.

### T6.3 35 hand-rolled `_staff()`, and 34 build a user no community can see — **medium** · [pre-existing]

The one that gets it right says why
(`tests/services/test_async_qualifier_backlog.py:36-44`): holding a role in a
tenant implies membership, which is the basis `UserRepository.get_community_people`
reads, and `UserRoleRepository.add` does not create it. So 34 modules test person
pickers and rosters against a shape production cannot produce. Independently
measured, the copies also diverge on the role row itself: 18 pass a tenant, 14
create a `UserRole` with no tenant at all, and 3 create no role row. (A
tenant-less `UserRole` is the SUPER_ADMIN shape; it only reads as staff here
because the harness stamps it — T6.1.) `tests/factories.py` exists for this and
its docstring concedes the field: "Those are intentionally left in place."

Alongside it, 22 local `make_user` shadow the canonical DB factory of the same
name, 11 of them synchronous mock builders, and
`tests/services/test_user_service.py:44-57` defaults `dm_notifications=False`
against a model default of `True` — so every `UserService` test runs against a
user with DMs off and any suppression branch is silently the default.

### T6.4 Five of six background workers have no test at all — **high** · [pre-existing]

Coverage: `async_qualifier_worker.py` 16%, `speedgaming_sync_worker.py` 28%,
`seed_roll_worker.py` 33%, `discord_event_worker.py` 36%,
`service_health_worker.py` 53%, against `race_room_worker.py` at 86% — the model
to copy. The qualifier worker's untested range holds both the feature-flag tenant
skip its docstring names as the CLAUDE.md carve-out and the logic deciding which
in-progress run gets auto-forfeited. `background_loop.py:59-60`, the
`except Exception` that keeps the loop alive, is uncovered too.

### T6.5 The flag tier surface is 72% covered, and every super-admin gate is in the gap — **critical** · [pre-existing]

Reproduced: `feature_flag_service.py 204 58 72%`, missing `158-176` (the
community's own Admin → Features read, `_ensure_staff` included), `221-242`
(`list_for_platform`, `_ensure_super_admin` included), `264-275` (the group
reads), and `346-350` — the guard refusing to un-default the sole default group.
Drop that guard and un-defaulting one group leaves every ungrouped tenant with no
availability tier, which is every gated feature dark platform-wide, with a green
suite.

### T6.6 Process-global worker state set without `monkeypatch` and restored only on the happy path — **high** · [pre-existing]

`tests/services/test_volunteer_reminder.py:17-23` sets
`reminder_mod._loop._task` and resets it *after* the assertion; if the assertion
fails the module-global keeps a `MagicMock` and `start()` becomes a permanent
no-op for the rest of that worker process. Same shape for the process-global
event dispatch queue at `tests/test_infra_coverage.py:69-95` and
`tests/services/test_discord_queue.py:194,205` — and with
`addopts = "-n auto --dist loadfile"`, other modules land on that worker.

### T6.7 Five never-awaited coroutines in a green run, and nothing can see them — **high** · [pre-existing]

Reproduced on a targeted run: `WebhookService._deliver_one`, a test-local
`handler`, and — the one that matters — `coroutine '_scoped' was never awaited`,
attributed to pytest's stash, i.e. a garbage-collection site rather than the
origin. `scoped()` is how every tenant read is scoped, so somewhere a test built
a scoped query and dropped it. `[tool.pytest.ini_options]` has no
`filterwarnings` and no `--strict-markers`, and CI runs `pytest -q`, so several
hundred warnings scroll past.

**Fix:** `filterwarnings = ["error::RuntimeWarning", "default"]`, then bisect the
`_scoped` origin.

### T6.8 A dedicated CI job that passes when it runs nothing — **high** · [pre-existing]

`tests/services/test_bracket_swiss_crossvalidation.py:148-152` skips on a missing
`BBPPAIRINGS_BIN`, and `.github/workflows/test.yml:154` runs that file as its own
lane. If the upstream build output is renamed, all six cross-validation cases
skip and the job whose only purpose is those six reports success.

**Fix:** `test -x "$BBPPAIRINGS_BIN"` as a step before pytest.

### T6.9 The network guard has no self-test — **high** · [pre-existing]

`tests/conftest.py:109-134` exists because "a service-health test once POSTed to
five third-party production hosts on every CI run". Nothing asserts it still
blocks; one `pytest.raises(RuntimeError, match='External network access blocked')`
would pin it.

### T6.10 Fifteen modules run on a second async runner supplied by an undeclared dependency — **medium** · [mixed]

`asyncio_mode = "auto"` is configured, yet 15 modules carry
`pytestmark = pytest.mark.anyio` — 12 of them the async-qualifier suite — and
**`anyio` is not declared in `pyproject.toml`** in either group; it arrives
transitively through httpx/starlette/mcp. There is no `anyio_backend` fixture, so
the backend is anyio's default, and `tests/mcp/conftest.py` already documents
that the two runners differ on which task drives async-fixture teardown.

### T6.11 Untested branches on the money and pool-clearing paths — **critical** · [new]

`payout_service.py:42` — the `10 <= place % 100 <= 20` arm of `_ordinal`; only
places 1/2/3 are ever exercised, so deleting the branch exports "11st place" with
a green suite. `:346` — `_validate_money(None) → None`, the documented "`None`
clears a value, which is not the same as zero"; `set_pool(id, None, None, actor)`
is never called, so a regression coercing `None → Decimal(0)` turns "nobody has
decided" into "the decision was nothing" in the pasted block. `:366` — the
one-person-twice-at-a-place refusal is reached only through `set_entrant`'s
separate check. *[reviewer-measured.]*

### T6.12 Smaller gaps, same shape — **medium**

`mark_in_progress` (`async_qualifier_live_race_service.py:216-223`) is entirely
unreached — the test named for it covers `race_room_service`'s same-named method.
`record_manual_finish`'s bad-status refusal (`:313`) is untested while its
empty/duplicate/no-time siblings are. `enable_all_flags` (conftest) and
`enable_all_features` (`api_helpers.py:86`) are the same body under two names,
7 files using one and 2 the other. Six tenancy modules hand-roll the second
tenant that `two_tenants` exists to provide, and one of them
(`test_tournament_signup_isolation.py:57`) already drives a service under a
flag-off tenant, one `@requires_feature` from a pass for the wrong reason.
`tests/services/test_feedback_service.py:71` asserts `feedback.id == 1`.

---

## T7 — Dead code and doc drift

### T7.1 Two unbounded-growth tables have housekeeping nobody calls — **medium** · [pre-existing]

`mcp_auth_repository.purge_expired_codes:90` and
`webhook_delivery_repository.prune_older_than:48` have no service, worker or
route caller — only the repository-coverage test. Neither
`docs/features/webhooks.md` nor `docs/features/mcp-server.md` mentions retention,
so this reads as retention that exists. `mcp_authorization_code` and
`webhook_delivery` grow forever.

### T7.2 A half-built tenant delete, kept alive by a test allowlist — **low** · [pre-existing]

`TenantRepository.delete:80` has no caller, and of 230 `AuditActions` exactly two
are never written — `TENANT_DELETED` and `CHALLONGE_WEBHOOK_SYNCED` (independently
confirmed). Both survive only inside `_EXCLUDED_BY_DESIGN` in
`test_event_audit_parity.py`, which is what keeps
`test_no_untriaged_audit_actions` green.

### T7.3 Four dead predicates and passthroughs — **low** · [mixed]

`notification_links.admin_qualifier_queue:196` **[new, `7a4e049`]** — its one
consumer calls `link_for_tenant` directly and duplicates the label;
`match_status.is_live:215`; `tournament_service.get_tournaments_by_ids:603` (a
pure passthrough); `models/tournament.py:330 ProviderTask.is_terminal`. Enum
members and CSS are clean: 0 of 114 enum members and 0 of 93 `.wiz-*` classes are
unreferenced. *[reviewer-measured.]*

### T7.4 `docs/reference/data-model.md` documents the migration chain 19 migrations short — **medium** · [new]

`:1741` — "The head is **migration 53**". The head is **72**, from 74 files, and
nothing about 54–72 (station layout, payouts, room tokens, the qualifier window
state, live-race handles) is in the reference. `docs/current-state.md:82` already
cites migration 65, so the two docs disagree.

**Fix:** replace the enumerated tail with a pointer to `migrations/models/`,
honouring the no-hand-maintained-counts rule in `docs/README.md:86`.

### T7.5 The MCP tool counts are wrong in the doc that states them twice — **low** · [new]

`docs/features/mcp-server.md:17,18,319` say 19 writes and 54 reads; the
catalogue snapshot the tests assert against holds **21** and **56**. The two
extras are `sign_up_for_tournament` / `withdraw_from_tournament`, registered in
`mcpserver/tools/tournaments.py`, not `match_writes.py` — and the doc's own write
table at `:333` lists them, so `:17` contradicts `:333`.

### T7.6 `docs/current-state.md` contradicts itself on the help-article count — **low** · [mixed]

`:27` says ten articles, `:50` says nine, and there are 10.
`docs/README.md:86` forbids hand-maintained counts for exactly this reason.

### T7.7 Module-size watch — **low**

Nothing exceeds the 800-line soft limit except the two baselined files (T1.3).
Five are within 50 lines: `pages/platform.py` 788,
`application/services/discord/discord_service.py` 785, `theme/tables/match.py`
779, `application/services/match/match_service.py` 759,
`application/services/match_reschedule_service.py` 747. `discord_service.py` is
the natural first split — it holds eight of the tree's guild/role/event
`except Exception as e: return False, …` wrappers along an obvious
reads/role-writes/event-writes seam. `scripts/mypy_baseline.json` carries 1,389
errors across 180 files, shrinking.

---

## Cross-cutting themes

**The second copy is written after the primitive exists.** Not one finding in T4
is "nobody extracted this". In every case the shared helper predates the copy,
often by days, and sometimes in the same file (`env_flag`, T4.9) or the same
function (`notify_error`, T4.4). The mechanism is discoverability, not
discipline — which is why the remediation that sticks is a hook naming the
primitive in its block message, and why `check_dry_regressions` is the right idea
sitting on a broken payload (T1.1).

**A comment describing a protection is not a protection.** Four findings turn on
prose that asserts an enforcement the code does not have:
`theme/dialog/match_dialog.py:65` ("`RaceRoomService` then refuses" — it does
not, T5.1), `_bracket/scheduling.py:139` (naming the link picker as a caller the
guard protects, in the one path missing the guard, T3.2),
`crew_service.py:269` ("widened both ways", but the query is not, T5.11), and
`async_qualifier_live_race_service.py:424` ("cleared when nobody is left
unmatched", but the manual path always clears, T2.1). Each comment was true when
written. Each is now the most misleading line in its file.

**`getattr(x, 'name', None)` converts a rename into a null.** T2.3's two tools
answer `null` for the fields a caller asked for because the defaults absorb the
rename. The same shape is one `except Exception: return []` away from T2.5. A
defensive default on a field you own is not defence, it is a silent failure that
no error handler can see.

**The tenancy story is genuinely solid, and its guards are load-bearing.** 61
scoped models, 0 unstamped production writes, 3 unscoped entry-surface reads of
which 2 are the documented cross-tenant discovery path and 1 is safe-by-caller
(T5.6). The leak-test ratchet has kept pace with every model added in the window.
The two soft spots are both about the guard's reach rather than the code:
`check_tenant_scoping` does not inspect `api/`, and the test harness fills in the
stamp production must write (T6.1).

**The calls-to-action rule is enforced at the builder and lost at the edges.**
`notification_links.py` does its job — one construction site outside the module,
`link_for` never raises, every builder docstring names the control it targets. The
two failures are downstream of it: login discards the query string that *is* the
control (T2.6), and a page that returns early skips the stale-link report the same
file installed three of (T5.14). A rule enforced only where the link is built
cannot see what happens to the link afterwards.

**Feature flags are the one convention where UI-only gating still passes review.**
CLAUDE.md says it plainly and the hook is supposed to enforce both halves, but
the hook skips a class with no decorators (T1.4) — so the one subsystem gated only
in the UI is invisible to the check written to find it.

---

## Remediation, ordered by debt removed per unit of effort

Safest first. Each wave should leave the tree green on its own.

**Wave 1 — repair the guards (mechanical, no behaviour change).**
T1.1 sweep payload · T1.3 baseline arithmetic · T1.2 factory allowlist ·
T1.4 gating-hook skip · T1.5 pick one authority on router preloads ·
T1.6 leak ratchet reads code · T1.7 migration prefix uniqueness ·
T6.7 `filterwarnings` and `--strict-markers`. Nothing here touches application
code, and everything after it lands with a net that works.

**Wave 2 — the bugs that produce a wrong result a person acts on.**
T2.1 unmatched erasure · T3.1 the DONE entrant with no time · T4.1 volunteer hours
together with T5.18, the `update_shift` overlap re-check that makes it reachable.
Small diffs with clear tests; each one currently misleads someone making a
decision.

_[`573fef2` shipped the four `ce73311` findings ahead of their waves, since they
were one commit old and share a file: T2.1 and T3.1 from this wave, plus T5.12 and
T2.2 from wave 6. Guarded by
`tests/services/test_async_qualifier_live_race_drift_findings.py`. Wave 2's
remainder — T4.1 with T5.18 — is untouched.]_

**Wave 3 — close the gates.**
T5.1 flag enforcement in `RaceRoomService` · T5.2 `load_community_user_or_404` ·
T5.3 push the enrollment gate into the service · T5.5 bound the two lists ·
T5.6 scope the reload · T5.13 the right exception types · T2.6 and T5.4 together
(carry the query string, and harden the validator that then receives it).

**Wave 4 — the extractions.**
T4.2 `_dm_opt_ok` inside `send_dm` · T4.4 `notify_error` everywhere plus its hook ·
T4.6 `Page[T]` and `PageParams` · T3.3 one finish-time validator ·
T3.2 `_require_schedulable` · T4.7/T4.8/T4.9/T4.10/T4.11 the constant and helper
collapses.

**Wave 5 — the test holes the earlier waves depend on.**
T6.2 route ratchet plus `/record`'s four tests · T6.5 the flag gates ·
T6.11 the payout branches · T6.4 one `_tick` test per worker · T6.3 `make_staff`
and the 35 collapses · T6.1 promote the tenant-stamp scan to a ratchet ·
T6.8/T6.9 the two CI lanes that can pass silently.

**Wave 6 — presentation honesty.**
T5.7 revert the refused switch · T5.8 the twelve confirmations ·
T5.15 the qualifier window prefill · ~~T5.12 the knowable precondition~~ ·
~~T2.2 name the skipped row~~ (both shipped in `573fef2`) · T5.14 the two quiet
deep links ·
T2.4 the silent truncation · T4.12/T4.13/T4.14 the dialog and card primitives.

**Wave 7 — housekeeping.**
T7.1 schedule or delete the two purges · T7.2/T7.3 the dead code ·
T7.4/T7.5/T7.6 the doc counts · T7.7 split `discord_service.py`.

### Feeding `/guardrail-audit`

Mechanically detectable classes that recurred here, each with the primitive to
name in the block message:

| Class | Check | Primitive to name |
|---|---|---|
| Hand-rolled `ui.notify(str(e))` in `pages/`/`theme/` | new hook, modelled on `check_table_prefs.py` | `theme/notify.py:notify_error` |
| A local test factory named `_staff`/`_player`/`_tournament`/`_match` | extend `check_dry_regressions` (T1.2) | `tests/factories.py:make_staff` |
| A truthy-env comparison outside `environment.py` | extend the existing `env-truthiness-literal` rule to multi-line | `application/utils/environment.py:env_flag` |
| A `.create()`/`bulk_create` on a scoped model with no tenant kwarg, anywhere in the tree | ratchet test (T6.1), not just the changed-file hook | `application/repositories/_tenant.py` |
| An API route with no test | ratchet test over `build_api_app().routes` (T6.2) | `tests/mcp/test_mcp_catalogue.py` as the model |
| Duplicate migration sequence prefix | `enforce_migration_safety.py` (T1.7) | — |

Judgment-level classes for `.claude/agents/architecture-reviewer.md`: a comment
asserting an enforcement the code does not perform; a `getattr(obj, 'name',
default)` on a type the module owns; a second capture path for one upstream
event; and UI-only feature gating where the flag spec names a service module.

---

## Positives worth preserving

A remediation wave must not refactor these away. Each entry says what breaks if
someone inlines it.

| Asset | What breaks if it goes |
|---|---|
| `.claude/scripts/` (29 hooks) + `scripts/guardrails.py` + `tests/test_guardrail_ci_parity.py` | The reason this audit's clean bills are clean. `EXCLUDED_CHECKS` is data so parity can be asserted. Fix T1.1/T1.3 **inside** the runner; do not replace it. |
| `application/errors.py` — `NotFoundError(ValueError)`, `FeatureDisabledError(NotFoundError)`, `require_found` at 130 sites | The `ValueError` base is deliberate so existing UI handlers keep catching. T5.13 is only worth fixing because this exists. |
| `api/dependencies.py:220-252` `ServiceErrorRoute` + `mcpserver/errors.py:31-49` | One ordered error mapping across 255 routes. `NotFoundError` is checked before `ValueError` because it subclasses it — reversing those two lines turns every 404 into a 400. |
| `api/dependencies.py:32` `tenant_context_scope`, `:64` `resolve_token`, `:200` `require_feature` | The API is excluded from `TenantMiddleware`, so this is the only tenant reset. A token-derived tenant leaking to the next request on a reused task is a cross-tenant read with no code change. |
| `api/_helpers.py:42` `load_community_user_or_404` | Reopens the leak `bebb35b` closed. Its docstring is the spec — do not trim it. T5.2 is a call site that ignored it. |
| `mcpserver/registry.py:56` `register` | Derives `readOnlyHint` structurally from `write=`, binds `tenant_scope` + `tz_scope`, and asserts the wrapped signature matches so `func_metadata` cannot publish an empty schema. That assert is load-bearing. |
| `mcpserver/auth.py:105` `authorize` | Gate order feature → membership → connection → role, with `NotFoundError` worded identically to an unknown slug. Reordering turns error text into a directory of the platform's communities. |
| `application/repositories/_tenant.py` + `_base.py` | The whole scoping surface is one file wide. `require_tenant_id()` raising is the safety net; a defensive `or None` there converts every forgotten scope into a silent cross-tenant read. |
| `application/utils/background_loop.py` | `for_each_tenant_scoped` binds `tenant_scope` **and** `tz_scope` per item. Inlining it is how a worker starts telling every community the same wrong time, and how one tenant's failure kills the batch. |
| `application/services/match/match_status.py` | One derived status vocabulary, ORM-free and Protocol-typed, shared by services, REST, Discord and pages. `STATUS_TONES` is the single colour source; splitting it re-creates "bracket says Scheduled, schedule says In Progress". |
| `application/services/reporting_shared.py`, `availability_windows.py`, `volunteer_hours.merged_hours`, `application/utils/duration.py` | The four modules whose whole purpose is that two surfaces cannot disagree. T4.1/T4.8/T4.15 are drifts *away* from them; the fix is more use, never a new local helper. |
| `application/services/notification_links.py` + `application/utils/app_links.py` | `link_for` never raises, deliberately — a throwing builder would take the whole DM down. This is the enforcement behind CLAUDE.md's calls-to-action rule. |
| `async_qualifier_draw.recompute_par_and_scores` — the par+scores transaction | Its docstring names the undetectable state it prevents: a fresh par beside stale scores, where every row looks individually plausible. T5.10 asks its callers to adopt the same discipline. |
| `theme/notify.py`, `theme/dialog/_helpers.py`, `theme/tables/mobile_grid.py`, `theme/tables/match_access.py`, `theme/connection.py`, `theme/notice.py`, `theme/realtime.py` | The presentation primitives the drift findings all point back toward. In `mobile_grid`, `customize_table` is the last statement **on purpose** so a column preference cannot hide the mobile card; `MatchBoardAccess`'s per-gate fields replaced a single `can_crud` boolean that handed 37 lifecycle controls to a coordinator every service refused. |
| `tests/conftest.py` template-restore harness (`:229-352`) + `tests/test_fixture_performance.py` | ~1ms per-test DB reset instead of ~31ms, and one `Tortoise.init()` per worker. This is why 5,613 tests run in 27.8s. Do not simplify the detached `sqlite3` template or the aiosqlite inline-execute patch. |
| `tests/tenancy/test_leak_test_coverage.py` (incl. `test_backlog_is_current`), `tests/test_query_budget.py`, `tests/services/test_event_audit_parity.py`, `tests/test_seed_coverage.py`, `tests/mcp/test_mcp_catalogue.py` | The five ratchets that catch what the unit suite structurally cannot. The query budget's shape assertion (small == large) matters more than its ceiling — do not replace it with a bigger constant. |
| `tests/factories.py:44` `make_audit_double` | Runs the real `write_and_publish` body against a mocked `write_log`, so a service converted to the paired call still emits events under test. A blanket `MagicMock()` undoes it. |
| The `xfail(strict=True)` ledger convention | Zero `xfail` in the tree today, because the last file using it retired its markers when the findings shipped. The convention lives only in prose — worth a hook if it recurs. |
| `scripts/mypy_ratchet.py` + `scripts/mypy_baseline.json` | Per-file: existing ORM-shape debt stays, new debt cannot land. |

---

## Method notes and limits

Every count in this file that is not marked *reviewer-measured* was produced by a
command run against HEAD during reconciliation, and the citations were re-read at
the quoted line. Six consequences were established by probing the real services
through the test harness rather than by reading: the unmatched-handle erasure
(T2.1), the vanishing racetime finisher (T3.1), the tenant-stamp behaviour of the
`db` fixture (T6.1), the two coverage numbers in T6.5, the roster-against-export
hours split and the `update_shift` overlap (T4.1, T5.18), and the runtime
`protected_routes` set behind T5.4. All probe files were deleted; no test in the
tree was modified.

What this audit did not do: run the app in a browser (the last three audits did,
and the presentation findings here are code-read except where they cite a
measured count), profile anything, or read the 1,389 mypy baseline entries for
findings. Severity reflects consequence to a person using the app, not
implementation ugliness — several of the mediums are cleaner code with no user
visible today, and are ranked accordingly.
