"""
Timezone Utilities

Handles timezone conversions for the application.
All datetimes are stored in UTC in the database and converted to/from US/Eastern for display.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

# Define the application timezone
EASTERN_TZ = ZoneInfo("America/New_York")


def now_eastern() -> datetime:
    """
    Get current datetime in US/Eastern timezone.
    
    Returns:
        Timezone-aware datetime in US/Eastern
    """
    return datetime.now(EASTERN_TZ)


def parse_eastern_datetime(date_str: str, time_str: str) -> datetime:
    """
    Parse date and time strings as US/Eastern and return as UTC.
    
    Args:
        date_str: Date string in format YYYY-MM-DD
        time_str: Time string in format HH:MM (24-hour)
        
    Returns:
        Timezone-aware datetime in UTC
        
    Raises:
        ValueError: If date/time format is invalid
        
    Example:
        >>> dt = parse_eastern_datetime('2025-01-15', '14:30')
        >>> # Returns datetime in UTC that represents 2:30 PM Eastern on Jan 15, 2025
    """
    try:
        # Parse as naive datetime
        naive_dt = datetime.strptime(
            f"{date_str} {time_str}",
            "%Y-%m-%d %H:%M"
        )
        
        # Localize to Eastern timezone
        eastern_dt = naive_dt.replace(tzinfo=EASTERN_TZ)
        
        # Convert to UTC for storage
        utc_dt = eastern_dt.astimezone(timezone.utc)
        
        return utc_dt
    except ValueError as e:
        raise ValueError(f"Invalid date/time format: {e}") from e


def to_eastern(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a datetime to US/Eastern timezone.
    
    Args:
        dt: Datetime to convert (can be naive or aware)
        
    Returns:
        Timezone-aware datetime in US/Eastern, or None if input is None
        
    Note:
        - If dt is naive, assumes it's UTC
        - If dt is already aware, converts to Eastern
    """
    if dt is None:
        return None
    
    # If naive, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Eastern
    return dt.astimezone(EASTERN_TZ)


def format_eastern_datetime(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    Format a datetime in US/Eastern timezone.
    
    Args:
        dt: Datetime to format (can be naive or aware)
        fmt: strftime format string
        
    Returns:
        Formatted string in Eastern time, or empty string if dt is None
    """
    if dt is None:
        return ''
    
    eastern_dt = to_eastern(dt)
    return eastern_dt.strftime(fmt)


def format_eastern_date(dt: Optional[datetime]) -> str:
    """
    Format just the date portion in US/Eastern timezone.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Date string in YYYY-MM-DD format, or empty string if None
    """
    return format_eastern_datetime(dt, "%Y-%m-%d")


def format_eastern_time(dt: Optional[datetime]) -> str:
    """
    Format just the time portion in US/Eastern timezone.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Time string in HH:MM format (24-hour), or empty string if None
    """
    return format_eastern_datetime(dt, "%H:%M")


def format_eastern_display(dt: Optional[datetime]) -> str:
    """
    Format datetime for display with timezone indicator.
    
    Args:
        dt: Datetime to format
        
    Returns:
        Formatted string like "2025-01-15 14:30 EST" or empty string if None
    """
    if dt is None:
        return ''
    
    eastern_dt = to_eastern(dt)
    # %Z gives timezone abbreviation (EST or EDT depending on DST)
    return eastern_dt.strftime("%Y-%m-%d %H:%M %Z")
