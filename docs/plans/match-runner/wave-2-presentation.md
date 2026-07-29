# Wave 2 — convert the eleven template conditionals

**Read [README.md](README.md) first. Wave 1 must be merged** — the row dict must
already carry `runner`.

Still a pure refactor: every control appears and disappears exactly when it did
before. What changes is *why*. At the end of this wave `is_racetime` exists
nowhere.

| Task | Touches | Size |
|---|---|---|
| T2.1 | `match_slots.py` — 4 sites | small |
| T2.2 | `match_grid.py` — 7 sites | medium |
| T2.3 | drop `is_racetime` from the row dict | small |

Do T2.1 and T2.2 together in one commit — they are mirrors of each other and the
mobile-mirror rule means a reviewer wants to see both.

---

## The mapping

Apply this table mechanically. Each site is asking one of four questions; the
answer is the capability, never the runner's identity.

| Control | Today | Becomes |
|---|---|---|
| Check In button | `!props.row.is_racetime` | `props.row.runner.checks_in_players` |
| "racetime.gg" note | `props.row.is_racetime` (the `v-else`) | `!props.row.runner.checks_in_players` |
| Assign Stations | `!props.row.is_racetime` | `props.row.runner.assigns_stations` |
| Seed *Generate* | `!props.row.is_racetime` | `!props.row.runner.owns_seed` |

Note the third and fourth rows: today both are `!is_racetime`, and after this
wave they are two different flags. That is the whole point — a runner can own
the seed without abolishing stations, which is exactly the manual-remote case in
wave 4. **Do not collapse them back into one flag** because they happen to
agree today.

---

## T2.1 — `theme/tables/match_slots.py`

Four sites. Locate by template constant, not line number.

**`SEED_SLOT`** — the Generate button's `v-if` ends `&& !props.row.is_racetime`.
Replace that clause with `&& !props.row.runner.owns_seed`. Leave the
already-generated-seed branch and the `notifications_off` deliverability icon
alone.

`SEED_SLOT` is registered **raw** (`table.add_slot('body-cell-generated_seed',
SEED_SLOT)`), not through `_fill`. It carries no `__XX__` placeholder today —
keep it that way; everything you need is on `props.row`.

**`STATE_SLOT`**, Scheduled branch — currently a three-way split added by the
proctor-UX work:

```html
        <q-btn v-if="!props.row.is_racetime && props.row.players && props.row.players.length" …>Check In</q-btn>
        <span v-else-if="!props.row.is_racetime" class="st-neutral italic-note">awaiting players…</span>
        <span v-else class="st-neutral italic-note">racetime.gg…</span>
```

becomes:

```html
        <q-btn v-if="props.row.runner.checks_in_players && props.row.players && props.row.players.length" …>Check In</q-btn>
        <span v-else-if="props.row.runner.checks_in_players" class="st-neutral italic-note">
            awaiting players
            <q-tooltip>This match has no players yet</q-tooltip>
        </span>
        <span v-else class="st-neutral italic-note">
            {{ props.row.runner.label }}
            <q-tooltip>Managed by {{ props.row.runner.label }}</q-tooltip>
        </span>
```

The final branch now names the runner instead of hardcoding "racetime.gg", so a
third runner reads correctly with no further edit. **That needs `label` on the
row dict** — add it to the `runner` sub-dict in
`application/services/match/match_display_service.py` (wave 1 left it out; this
is the one field wave 2 adds).

**`PLAYERS_SLOT`** — the assign-stations button's `v-if` contains
`!props.row.is_racetime`. Replace with `props.row.runner.assigns_stations`. Keep
the `__IA__` and player-count clauses exactly as they are.

`STATE_SLOT` carries `__CC__` and **must** stay registered through `_fill` —
there is a comment above it saying so. Do not change how it is registered.

---

## T2.2 — `theme/tables/match_grid.py`

Seven sites, all mirrors of T2.1.

**`_SEED_DETAIL`** — two clauses, the outer `mgc-detail` `v-if` and the button's
`v-if`. Both end `&& !props.row.is_racetime` → `&& !props.row.runner.owns_seed`.

**`_ACTIONS`** — five sites:

- Check In button: `&& !props.row.is_racetime` → `&& props.row.runner.checks_in_players`
- "Awaiting players" note: same substitution
- "Managed by racetime.gg" note: `&& props.row.is_racetime` →
  `&& !props.row.runner.checks_in_players`, and the text becomes
  `Managed by {{ props.row.runner.label }}`
- Assign Stations button: `!props.row.is_racetime` → `props.row.runner.assigns_stations`
- The `.mgc-actions` wrapper `v-if` contains `!props.row.is_racetime && props.row.players && props.row.players.length`
  → `props.row.runner.assigns_stations && props.row.players && props.row.players.length`

That wrapper clause is load-bearing and was got wrong once already: it must
render whenever any child does, including the Finished "Awaiting confirmation"
chip and the "Needs review" block. The first disjunct (`state` in the four
lifecycle states) covers those, so changing only the stations clause is safe —
but re-read the whole expression before editing it, and check a **Confirmed**
match with no players does not gain an empty bordered actions row.

Update the module docstring's card-anatomy paragraph if it names racetime.

---

## T2.3 — Remove `is_racetime` from the wire

**Depends on:** T2.1, T2.2.

Delete the `'is_racetime'` key from `_format_match_for_display` and its comment.

Then prove nothing reads it:

```bash
grep -rn "is_racetime\b" --include=*.py theme/ pages/ application/ tests/
```

Expect **zero** hits (`is_racetime_enabled` is a different string and still
exists until wave 3). A hit in `tests/` means a test asserted the old key —
update it rather than reinstating the field.

---

## Tests

`tests/theme/test_match_slot_templates.py` already sweeps every registered slot
for surviving `__XX__` placeholders across the `can_crud` × `actions_first` ×
`discord_id` cross-product. Extend it rather than starting a new file:

```python
def test_no_template_mentions_racetime_by_name()
def test_check_in_is_gated_on_the_runner_capability()
def test_seed_generate_is_gated_on_owns_seed_not_on_stations()
```

The last one is the guard against the two flags being re-merged: assert the
Generate button's condition mentions `owns_seed` and **not** `assigns_stations`.

`test_no_template_mentions_racetime_by_name` should scan every registered
template string for the literal `racetime` (case-insensitive) and fail. That is
the mechanical proof this wave is complete, and it keeps a future contributor
from reintroducing a hardcoded integration name in a slot.

---

## Verify

The four surfaces, both widths. **Nothing may look different from wave 1** —
apart from the racetime note now reading `racetime.gg` because that is the
runner's `label` rather than a hardcoded string (verify the label renders, not
the key: `racetime.gg`, not `racetime`).

Specifically confirm, as `proctor_user` on `/t/default/volunteer/proctor-station`
and `staff_user` on `/t/default/admin/schedule`:

- an on-premises Scheduled row with players still offers **Check In**
- an on-premises Scheduled row with no players still says **awaiting players**
- a racetime Scheduled row still says **racetime.gg** and offers nothing
- a racetime row offers no **Generate** and no **Assign Stations**
- an on-premises row still offers both
- a Confirmed racetime row shows no empty actions row on mobile

Screenshot each at 430px too, and read the images back — a broken Vue expression
renders an empty cell rather than an error.

Commit as *"Gate match controls on runner capabilities, not on racetime"*.
