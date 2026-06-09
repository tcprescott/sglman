# Timezone Handling in SGLMan

## Overview

This application handles all datetime values in **US/Eastern (America/New_York)** timezone for consistency across tournament scheduling.

## Implementation

### Storage
- All datetimes are stored in the database in **UTC** (Coordinated Universal Time)
- Tortoise ORM `DatetimeField` stores timezone-aware datetimes

### User Input
- Users enter dates/times in **US/Eastern** timezone
- The `parse_eastern_datetime()` function converts user input from Eastern to UTC for storage

### Display
- All datetimes are displayed to users in **US/Eastern** timezone
- The `format_eastern_*()` functions convert UTC datetimes to Eastern for display

## Key Functions

Located in `application/utils/timezone.py`:

### Input Processing
- `parse_eastern_datetime(date_str, time_str)` - Parse user input as Eastern, return UTC for storage

### Output Formatting
- `format_eastern_datetime(dt, fmt)` - Format datetime in Eastern with custom format
- `format_eastern_date(dt)` - Format just the date portion (YYYY-MM-DD)
- `format_eastern_time(dt)` - Format just the time portion (HH:MM)
- `format_eastern_display(dt)` - Format with timezone indicator (e.g., "2025-01-15 14:30 EST")

### Utilities
- `now_eastern()` - Get current datetime in Eastern timezone
- `to_eastern(dt)` - Convert any datetime to Eastern timezone

## Daylight Saving Time

The timezone utilities automatically handle DST (Daylight Saving Time):
- **EST** (Eastern Standard Time) - UTC-5 (winter)
- **EDT** (Eastern Daylight Time) - UTC-4 (summer)

Python's `zoneinfo` module handles DST transitions correctly.

## Usage Examples

### Creating a Match
```python
from application.utils.timezone import parse_eastern_datetime

# User submits: date="2025-01-15", time="14:30"
# This represents 2:30 PM Eastern on Jan 15, 2025
scheduled_at = parse_eastern_datetime("2025-01-15", "14:30")
# scheduled_at is now a UTC datetime (19:30 UTC if during EST)

await match_service.create_match(
    tournament_id=1,
    scheduled_date="2025-01-15",
    scheduled_time="14:30",  # Eastern time
    player_ids=[1, 2]
)
```

### Displaying Match Times
```python
from application.utils.timezone import format_eastern_time, format_eastern_display

# match.scheduled_at is stored in UTC
# Display just the time in Eastern
time_str = format_eastern_time(match.scheduled_at)  # "14:30"

# Display with timezone indicator
full_str = format_eastern_display(match.scheduled_at)  # "2025-01-15 14:30 EST"
```

### Current Time
```python
from application.utils.timezone import now_eastern

# Get current time in Eastern timezone
now = now_eastern()
default_date = now.strftime('%Y-%m-%d')
default_time = now.strftime('%H:%M')
```

## Modified Files

The following files were updated to use timezone utilities:

- `application/services/match_service.py`
  - `create_match()` - Parses input as Eastern, stores as UTC
  - `update_match()` - Parses input as Eastern, stores as UTC
  - `_format_match_for_display()` - Formats datetimes in Eastern

- `theme/dialog/match_dialog.py`
  - Uses Eastern timezone for default date/time values
  - Pre-fills edit form with Eastern times

- `pages/home_tabs/stage_timeline.py`
  - Displays match times in Eastern timezone

## Testing

To test timezone conversion:
```python
from application.utils.timezone import parse_eastern_datetime, format_eastern_display

# Test: 2 PM Eastern on Jan 15, 2025
dt_utc = parse_eastern_datetime("2025-01-15", "14:00")
print(dt_utc)  # 2025-01-15 19:00:00+00:00 (UTC)

# Convert back to Eastern for display
eastern_str = format_eastern_display(dt_utc)
print(eastern_str)  # "2025-01-15 14:00 EST"
```

## Important Notes

1. **Always use timezone utilities** when working with user input/output for datetimes
2. **Database stores UTC** - never store localized times in the database
3. **User sees Eastern** - all displayed times should be in US/Eastern
4. **DST is automatic** - no manual DST handling needed

## Migration Considerations

If you have existing data in the database:
- Existing naive datetimes will be treated as UTC by the timezone utilities
- If existing data was entered as Eastern without timezone awareness, you may need a one-time migration to convert them properly
- Consider adding a migration script if historical data needs timezone correction

## Migration SQL
```sql
UPDATE `match`
SET scheduled_at = DATE_ADD(scheduled_at, INTERVAL 4 HOUR);
```