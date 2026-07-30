"""Whole-second duration parsing and display (``H:MM:SS``).

Split out of ``pages/qualifiers.py`` so the player page, the reviewer queue and
the REST layer agree on what a typed finish time means. Deliberately strict:
folding 1- and 2-segment input into base 60 made ``1:23`` mean 83 seconds, which
is the likeliest typo in a field labelled ``H:MM:SS`` and reads as correct
afterwards.

Pure syntax — the ``MAX_RUN_SECONDS`` ceiling is a service rule, so the hour
segment is unbounded here.
"""

__all__ = ['format_hms', 'parse_hms']

_SEGMENTS = 3
_MAX_SEGMENT = 59

_SHAPE = "Enter a finish time as H:MM:SS — for example 1:23:45."
_THREE_PARTS = ("Enter all three parts — H:MM:SS. "
                "1:23:45 is 1 hour 23 minutes 45 seconds.")
_NUMBERS = "Finish time must be numbers separated by ':'"
_SEGMENT_RANGE = "Minutes and seconds must be between 0 and 59."
_POSITIVE = "Finish time must be greater than zero."


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
    text = (text or '').strip()
    if not text:
        raise ValueError(_SHAPE)
    parts = text.split(':')
    try:
        nums = [int(p) for p in parts]
    except ValueError as e:
        raise ValueError(_NUMBERS) from e
    if len(nums) != _SEGMENTS:
        raise ValueError(_THREE_PARTS)
    if any(n < 0 for n in nums):
        raise ValueError(_SHAPE)
    hours, minutes, secs = nums
    if minutes > _MAX_SEGMENT or secs > _MAX_SEGMENT:
        raise ValueError(_SEGMENT_RANGE)
    total = hours * 3600 + minutes * 60 + secs
    if total <= 0:
        raise ValueError(_POSITIVE)
    return total
