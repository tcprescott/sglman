from datetime import date, datetime, timezone

import pytest

from application.utils.timezone import (
    EASTERN_TZ,
    format_eastern_date,
    format_eastern_datetime,
    format_eastern_display,
    format_eastern_time,
    now_eastern,
    parse_eastern_datetime,
    to_eastern,
)


class TestParseEasternDatetime:
    def test_winter_est_converts_to_utc(self):
        # EST is UTC-5, so 14:30 Eastern → 19:30 UTC
        dt = parse_eastern_datetime("2025-01-15", "14:30")
        assert dt.hour == 19
        assert dt.minute == 30

    def test_winter_result_is_utc_aware(self):
        dt = parse_eastern_datetime("2025-01-15", "14:30")
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == 0

    def test_summer_edt_converts_to_utc(self):
        # EDT is UTC-4, so 14:30 Eastern → 18:30 UTC
        dt = parse_eastern_datetime("2025-07-15", "14:30")
        assert dt.hour == 18
        assert dt.minute == 30

    def test_midnight_eastern_converts_correctly(self):
        # 00:00 EST → 05:00 UTC
        dt = parse_eastern_datetime("2025-01-15", "00:00")
        assert dt.hour == 5
        assert dt.minute == 0

    def test_invalid_date_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid date/time format"):
            parse_eastern_datetime("not-a-date", "14:30")

    def test_invalid_time_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid date/time format"):
            parse_eastern_datetime("2025-01-15", "99:99")

    def test_wrong_date_format_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid date/time format"):
            parse_eastern_datetime("01/15/2025", "2:30pm")

    def test_roundtrip_preserves_time(self):
        dt = parse_eastern_datetime("2025-06-15", "09:00")
        back = to_eastern(dt)
        assert back.hour == 9
        assert back.minute == 0

    def test_dst_before_spring_forward(self):
        # 01:59 on spring-forward day is unambiguously EST (UTC-5)
        dt = parse_eastern_datetime("2025-03-09", "01:59")
        assert dt.hour == 6
        assert dt.minute == 59

    def test_fall_back_midnight_is_edt(self):
        # 00:00 on fall-back day is unambiguously EDT (UTC-4)
        dt = parse_eastern_datetime("2025-11-02", "00:00")
        assert dt.hour == 4
        assert dt.minute == 0


class TestToEastern:
    def test_none_returns_none(self):
        assert to_eastern(None) is None

    def test_naive_datetime_treated_as_utc(self):
        naive_utc = datetime(2025, 1, 15, 19, 30)  # naive, interpreted as UTC
        result = to_eastern(naive_utc)
        assert result.hour == 14
        assert result.minute == 30

    def test_utc_aware_datetime_converts(self):
        utc_dt = datetime(2025, 7, 15, 18, 30, tzinfo=timezone.utc)
        result = to_eastern(utc_dt)
        assert result.hour == 14
        assert result.minute == 30

    def test_already_eastern_preserves_wall_clock(self):
        eastern_dt = datetime(2025, 1, 15, 14, 30, tzinfo=EASTERN_TZ)
        result = to_eastern(eastern_dt)
        assert result.hour == 14
        assert result.minute == 30

    def test_result_is_eastern_aware(self):
        utc_dt = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
        result = to_eastern(utc_dt)
        assert result.tzinfo is not None

    def test_naive_result_has_eastern_tzinfo(self):
        naive_utc = datetime(2025, 1, 15, 19, 30)
        result = to_eastern(naive_utc)
        assert result.tzinfo == EASTERN_TZ


class TestFormatEasternDate:
    def test_none_returns_empty_string(self):
        assert format_eastern_date(None) == ""

    def test_formats_utc_as_eastern_date(self):
        # 19:30 UTC on Jan 15 → Jan 15 in Eastern (14:30 EST)
        utc_dt = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
        assert format_eastern_date(utc_dt) == "2025-01-15"

    def test_utc_midnight_may_show_previous_date_in_eastern(self):
        # 00:01 UTC Jan 16 → 19:01 EST Jan 15
        utc_dt = datetime(2025, 1, 16, 0, 1, tzinfo=timezone.utc)
        assert format_eastern_date(utc_dt) == "2025-01-15"

    def test_format_is_yyyy_mm_dd(self):
        utc_dt = datetime(2025, 3, 5, 20, 0, tzinfo=timezone.utc)
        result = format_eastern_date(utc_dt)
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # year
        assert len(parts[1]) == 2  # month
        assert len(parts[2]) == 2  # day

    def test_accepts_plain_date(self):
        # Plain dates have no timezone; format them as-is.
        assert format_eastern_date(date(2025, 1, 15)) == "2025-01-15"

    def test_plain_date_is_not_shifted(self):
        # A date near year boundary should not roll based on UTC vs Eastern.
        assert format_eastern_date(date(2025, 12, 31)) == "2025-12-31"


class TestFormatEasternTime:
    def test_none_returns_empty_string(self):
        assert format_eastern_time(None) == ""

    def test_utc_to_eastern_time_winter(self):
        # 19:30 UTC → 14:30 EST
        utc_dt = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
        assert format_eastern_time(utc_dt) == "14:30"

    def test_utc_to_eastern_time_summer(self):
        # 18:30 UTC → 14:30 EDT
        utc_dt = datetime(2025, 7, 15, 18, 30, tzinfo=timezone.utc)
        assert format_eastern_time(utc_dt) == "14:30"

    def test_format_is_hh_mm_24_hour(self):
        utc_dt = datetime(2025, 1, 15, 0, 5, tzinfo=timezone.utc)
        result = format_eastern_time(utc_dt)
        parts = result.split(":")
        assert len(parts) == 2
        assert len(parts[0]) == 2  # zero-padded hour
        assert len(parts[1]) == 2  # zero-padded minute


class TestFormatEasternDisplay:
    def test_none_returns_empty_string(self):
        assert format_eastern_display(None) == ""

    def test_winter_shows_est_abbreviation(self):
        utc_dt = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
        assert format_eastern_display(utc_dt) == "2025-01-15 14:30 EST"

    def test_summer_shows_edt_abbreviation(self):
        utc_dt = datetime(2025, 7, 15, 18, 30, tzinfo=timezone.utc)
        assert format_eastern_display(utc_dt) == "2025-07-15 14:30 EDT"

    def test_result_includes_timezone_abbreviation(self):
        utc_dt = datetime(2025, 4, 1, 16, 0, tzinfo=timezone.utc)
        result = format_eastern_display(utc_dt)
        assert result.endswith("EST") or result.endswith("EDT")


class TestFormatEasternDatetime:
    def test_none_returns_empty_string(self):
        assert format_eastern_datetime(None) == ""

    def test_default_format_is_yyyy_mm_dd_hh_mm(self):
        utc_dt = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
        assert format_eastern_datetime(utc_dt) == "2025-01-15 14:30"

    def test_custom_format_is_respected(self):
        utc_dt = datetime(2025, 1, 15, 19, 30, tzinfo=timezone.utc)
        result = format_eastern_datetime(utc_dt, fmt="%H:%M")
        assert result == "14:30"


class TestNowEastern:
    def test_returns_eastern_aware_datetime(self):
        now = now_eastern()
        assert now.tzinfo == EASTERN_TZ

    def test_is_recent(self):
        before = datetime.now(timezone.utc)
        now = now_eastern()
        after = datetime.now(timezone.utc)
        now_utc = now.astimezone(timezone.utc)
        assert before <= now_utc <= after
