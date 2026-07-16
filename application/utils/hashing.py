"""Stable content hashing for cheap unchanged-since-last checks."""

import hashlib
import json


def stable_content_hash(obj) -> str:
    """Return a deterministic sha256 hexdigest of ``obj``.

    Serializes with sorted keys so equal payloads always hash identically,
    and falls back to ``str`` for values JSON can't encode natively (e.g.
    ``datetime``). Suitable for detecting whether a payload changed since a
    previously stored hash — not a security-grade digest.
    """
    blob = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()
