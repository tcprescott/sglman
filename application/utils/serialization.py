"""Small serialization helpers shared across entry surfaces."""

import json
from typing import Any, Optional


def decode_json_details(raw: Optional[str]) -> Any:
    """Decode a JSON-encoded detail blob, falling back to the raw string.

    Audit rows store ``details`` as text. Older rows (and any written by hand)
    may not be valid JSON, so a decode failure returns the string unchanged
    rather than raising — a detail field is context for a human, and losing the
    whole audit entry because its metadata is malformed would be the worse
    outcome.
    """
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw
