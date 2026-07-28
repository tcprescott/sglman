# Timezone Handling

**Store UTC, display US/Eastern.** Never persist a localized datetime; never render
a raw UTC one. Every conversion goes through
[`application/utils/timezone.py`](../application/utils/timezone.py).

## The utilities

| Function | Direction |
|---|---|
| `parse_eastern_datetime(date_str, time_str)` | user input (Eastern) → UTC, for storage |
| `format_eastern_datetime(dt, fmt)` | UTC → Eastern, custom format |
| `format_eastern_date(dt)` | UTC → `YYYY-MM-DD` |
| `format_eastern_time(dt)` | UTC → `HH:MM` |
| `format_eastern_display(dt)` | UTC → `YYYY-MM-DD HH:MM EST` |
| `now_eastern()` | current time, Eastern |
| `to_eastern(dt)` | any datetime → Eastern |

```python
from application.utils.timezone import parse_eastern_datetime, format_eastern_display

scheduled_at = parse_eastern_datetime("2026-01-15", "14:30")  # → 19:30 UTC
format_eastern_display(scheduled_at)                          # → "2026-01-15 14:30 EST"
```

## DST

`zoneinfo` handles the EST (UTC−5) / EDT (UTC−4) transition automatically — there is
no manual offset arithmetic anywhere in the codebase, and there should not be.
`tests/test_timezone.py` covers the boundary cases.

## Storage

The `*_at` columns were created as `TIMESTAMPTZ` in the initial schema, so stored
values have always been timezone-aware UTC. There is no legacy naive-Eastern data
and no shift-by-N-hours correction to apply.
