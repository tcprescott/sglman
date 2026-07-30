# Wave 1 — nothing is lost to one click

**Read [README.md](README.md) first.**

No migration, no new service method, no change to the draw or the clock. At the
end of this wave a competitor cannot forfeit by accident, cannot submit a time
60× too fast by dropping a segment, and the reviewer stops converting seconds in
their head.

| Task | Touches | Size |
|---|---|---|
| T1.1 | `application/utils/duration.py` — the shared parser/formatter | small |
| T1.2 | strict time entry + a live echo on the run card | medium |
| T1.3 | Forfeit behind `ConfirmationDialog` | small |
| T1.4 | the review queue reads `H:MM:SS` | small |
| T1.5 | tests + docs | small |

Closes **F3** (`1:23` means 83 seconds), the first half of **F1** (an
unconfirmed forfeit — the reattempt half is wave 3), and the raw-seconds part of
**F5**.

---

## T1.1 — One duration helper, in `application/utils/`

### Where it lives, and why

`application/utils/duration.py`, beside `timezone.py`.

`pages/qualifiers.py` owns both `_fmt_hms` and `_parse_hms` today
([`:27-53`](../../../pages/qualifiers.py#L27)), and the admin review queue —
which needs the formatter — cannot import a page. Two more surfaces want it
before this plan is done (wave 2's reviewer card, wave 3's runs list), so it
moves once, now.

It is **pure syntax**: no I/O, no imports from `application/services` or
`models`. In particular it does **not** enforce `MAX_RUN_SECONDS` — that ceiling
is a service rule, `submit_run` already applies it with a good sentence, and a
week is `168:00:00`, so the hour segment stays unbounded here.

### The module

```python
"""Whole-second duration parsing and display (``H:MM:SS``).

Split out of ``pages/qualifiers.py`` so the player page, the reviewer queue and
the REST layer agree on what a typed finish time means. Deliberately strict:
folding 1- and 2-segment input into base 60 made ``1:23`` mean 83 seconds, which
is the likeliest typo in a field labelled ``H:MM:SS`` and reads as correct
afterwards.
"""

_MAX_SEGMENT = 59


def format_hms(seconds: int | None, *, dash: str = '—') -> str:
    """``4325`` → ``'1:12:05'``; ``None`` → ``dash``."""
    if seconds is None:
        return dash
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}'


def parse_hms(text: str) -> int:
    """Parse exactly ``H:MM:SS`` into whole seconds. Raises ``ValueError``."""
```

`parse_hms`'s contract, as a table — write the tests from it directly:

| Input | Result |
|---|---|
| `1:23:45` | `5025` |
| `0:07:30` | `450` |
| `168:00:00` | `604800` (the hour segment is unbounded) |
| `''` / whitespace | *"Enter a finish time as H:MM:SS — for example 1:23:45."* |
| `abc`, `1:ab:00` | *"Finish time must be numbers separated by ':'"* |
| `83`, `1:23` | *"Enter all three parts — H:MM:SS. `1:23:45` is 1 hour 23 minutes 45 seconds."* |
| `1:2:3:4` | same three-parts sentence |
| `-1:00:00`, `1:-2:00` | *"Enter a finish time as H:MM:SS."* |
| `1:99:00`, `1:00:99` | *"Minutes and seconds must be between 0 and 59."* |
| `0:00:00` | *"Finish time must be greater than zero."* |

Two of those sentences are today's wording and must not regress (`abc` and the
zero case) — the review measured them as *working*. The two new sentences are
the point of the task: each names the shape rather than restating the label.

`format_hms(0)` now returns `'0:00:00'` where `_fmt_hms(0)` returned `'—'`.
That is intentional: a zero-second row is data, not a missing value, and the
only caller that can see zero is a forfeited run's score column, not its time.

### Wiring

Delete `_fmt_hms` / `_parse_hms` from `pages/qualifiers.py` and import the
helpers. Leave the `_fmt` (datetime) helper where it is — it is a one-line
wrapper over `format_eastern_display` and unrelated.

### Tests

`tests/test_duration.py` — top level, mirroring `tests/test_timezone.py`, which
is the existing home for `application/utils/timezone.py`'s tests (there is no
`tests/utils/` package, and pure-helper tests live either at the top level or as
a class in `tests/test_utils_coverage.py`; pick the former, this module earns its
own file).

One test per row of the table above, asserting the **exact** message for each
failure. A `pytest.mark.parametrize` over `(text, seconds)` and a second over
`(text, message)` is enough; no DB, no fixtures.

---

## T1.2 — `H:MM:SS` means `H:MM:SS`, and the field says what it read

**Depends on:** T1.1. **File:** `pages/qualifiers.py`, `_render_active_run`
([`:154-203`](../../../pages/qualifiers.py#L154)).

### Change

The strict parser alone would turn a dropped segment into an error message,
which is most of the fix. Add the echo so the *other* direction — the parse
succeeded but not as the runner meant it — is visible before they commit:

```python
                time_in = ui.input('Finish time (H:MM:SS)', placeholder='1:23:45').classes('w-full')
                echo = ui.label('').classes('text-caption text-grey')

                def _echo() -> None:
                    try:
                        seconds = parse_hms(time_in.value)
                    except ValueError:
                        echo.text = ''
                        return
                    echo.text = f'Submitting {format_hms(seconds)} — {_words(seconds)}'

                time_in.on_value_change(_echo)
```

`_words(5025)` → `'1 hour, 23 minutes, 45 seconds'` (singular/plural correct,
zero segments omitted, `'45 seconds'` for `0:00:45`). Put `_words` next to the
input handler in the page, not in the util — it is display copy for one field,
and the util stays free of prose.

**Confirm `on_value_change` against `nicegui/llms.md`** inside the installed
package before writing it; if the 3.x surface differs, wire the same handler to
whatever that file documents rather than guessing.

The echo stays empty while the value does not parse — the error sentence is the
feedback then, and it arrives on Submit. Do not notify while typing.

### Also in this task

Route the three `ui.notify(str(e), color='warning')` calls in this page
(`_start`, `_submit`, `_forfeit`) through `notify_error` — the convention
`theme/notify.py` documents, and the reason a long validation sentence gets a
dismissable multi-line toast instead of being truncated at five seconds.

### Tests

The parser's behaviour is covered by T1.1. What needs a test here is that the
page uses it: `tests/test_qualifiers_page.py` (top level, the way
`tests/test_equipment_labels_page.py` covers a page today) asserting
`pages.qualifiers` exposes no local `_parse_hms` and imports `parse_hms` from
`application.utils.duration`. That reads like a tautology and is not — it is
what stops the local copy being reintroduced by a later edit.

Browser-verify the echo by typing `1:23`, then `1:23:45`, then `1:00:99`.

---

## T1.3 — Forfeit asks first

**File:** `pages/qualifiers.py`, `_forfeit` and the button row
([`:192-203`](../../../pages/qualifiers.py#L192)).

### Change

```python
                def _confirm_forfeit() -> None:
                    ConfirmationDialog(
                        title='Forfeit this run?',
                        message=(
                            'Forfeiting ends this attempt now.\n\n'
                            'The run scores 0, the pool slot is spent, and this '
                            'cannot be undone.'
                        ),
                        confirm_text='Forfeit run',
                        tone='negative',
                        on_confirm=_forfeit,
                    ).open()
```

and point the button at `_confirm_forfeit`. `_forfeit` itself keeps its
`try/except` and must `dialog.close()` before refreshing — `ConfirmationDialog`
does not close itself when `on_confirm` is supplied
([`confirmation_dialog.py:32-35`](../../../theme/dialog/confirmation_dialog.py#L32)),
so capture the instance and close it in the handler. Check how
`pages/home_tabs/api_tokens_section.py` does this and follow it rather than
inventing a second shape.

`tone='negative'` and a `title` that names the action, per the dialog's own
docstring and `tests/theme/test_confirmation_dialog_tone.py`.

### What this message does not say yet

Not *"you have 1 reattempt remaining"*. That number needs a service read that
does not exist until wave 3 (T3.3), and a message that promises a remedy the
page cannot offer is worse than one that does not mention it. Wave 3 adds the
sentence; this wave states only what is true today.

### Tests

`tests/theme/test_confirm_result_copy.py` is the existing home for
confirmation-copy assertions — add the forfeit message there if it fits its
shape, otherwise assert in the page test that the forfeit button's handler is
not `_forfeit` directly. Browser-verify: click **Forfeit**, cancel, confirm the
run is still in progress and the clock still ticking; then confirm and check the
row reads `forfeit` / `approved` / score `0`.

---

## T1.4 — The reviewer stops doing arithmetic

**Depends on:** T1.1. **File:** `pages/admin_tabs/admin_qualifiers.py`,
`_render_queue` ([`:439`](../../../pages/admin_tabs/admin_qualifiers.py#L439)).

```python
                    ui.badge(format_hms(run.elapsed_seconds), color='blue')
```

`362439s` becomes `100:40:39`, `6000s` becomes `1:40:00`, and a null time keeps
its `—` from `format_hms`'s `dash`. One line, and it is the difference between a
reviewer reading the number and computing it.

The rest of F5 — timestamps, the permalink played, the runner's other runs, the
note field — is wave 2 (the measured duration) and wave 3 (the card rebuild).
Do not start the rebuild here; this task is the formatter only.

Also apply `format_hms` to the `par {pl.par_time}s` badge in `_render_pools`
([`:274`](../../../pages/admin_tabs/admin_qualifiers.py#L274)) — same raw-seconds
problem, same one-line fix, and par is compared against run times by eye.

---

## T1.5 — Docs

- [`docs/features/online-tournaments.md`](../../features/online-tournaments.md)
  — in the async-qualifier section: the finish time is typed as `H:MM:SS` and all
  three segments are required; forfeit is confirmed and irreversible.
- [`docs/reference/services.md`](../../reference/services.md) — if it lists
  utility modules, add `application/utils/duration.py` (`parse_hms`,
  `format_hms`) and say the strictness is deliberate.

No data-model or REST doc changes in this wave — nothing stored or exposed
changed.

---

## Wave 1 wrap-up

```bash
poetry run pytest
grep -rn "_parse_hms\|_fmt_hms" --include=*.py pages/ theme/ application/
```

The grep must return nothing: a surviving local copy is the failure mode this
wave exists to prevent, and there were two of them (one of which formatted
nothing at all — the reviewer's `NNNNNNs`).

Then, in two browser contexts at 1500px and 390×844:

1. As `player_two`, start a run. Type `1:23` → the three-parts sentence. Type
   `83` → the same. Type `1:00:99` → the segment sentence. Type `1:23:45` → the
   echo reads *"Submitting 1:23:45 — 1 hour, 23 minutes, 45 seconds"*.
2. Click **Forfeit** → dialog → **Cancel** → the run is still live and the clock
   still ticking (this is the regression that would matter most).
3. Submit a real time; as `staff_user`, open the Review Queue and confirm the
   badge reads `H:MM:SS` for both a short and a very long run.

Commit as *"Confirm a qualifier forfeit and require a full H:MM:SS finish time"*.
