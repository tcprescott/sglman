"""Tiny in-process cache for whole rendered HTML pages.

Built for the public, anonymous, read-only surfaces (the static bracket views):
one render is valid for *every* viewer, so the expensive part — the queries and
the markup — should happen once per change, not once per spectator.

Freshness comes from two independent guards, because either alone is wrong here:

* a **per-tenant version counter** the caller bumps when something changed
  (the bracket views bump it from the event bus), which makes a report visible
  on the next request rather than at the end of a TTL; and
* a **TTL**, which bounds staleness for the changes no event announces — a
  match's scheduled time passing, so a card's derived status moves from
  "scheduled" to "imminent" with no write anywhere.

Entries carry a strong ``ETag`` of the body so a returning reader (the pages
reload themselves on a timer) usually gets a 304 with no body at all.

Deliberately process-local and dependency-free: the app runs a single worker
(docs/scaling-roadmap.md), and a shared cache is that document's problem, not
this module's. Nothing here is tenant-aware beyond the key — callers pass the
tenant in, and entries for one tenant can never satisfy another's key.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

__all__ = ['CachedPage', 'HtmlPageCache']


@dataclass(frozen=True)
class CachedPage:
    """A rendered page plus the validators a response needs."""

    body: str
    etag: str
    stored_at: float
    version: int


class HtmlPageCache:
    """Keyed HTML cache with a TTL and per-tenant invalidation.

    ``ttl_seconds`` bounds how long an un-invalidated entry may be served.
    ``max_entries`` is a hard bound on memory: the oldest entries are dropped
    when it is exceeded (insertion-ordered dict, so this is FIFO — for a set of
    pages that are all cheap to re-render, that is enough).
    """

    def __init__(self, *, ttl_seconds: float = 30.0, max_entries: int = 256):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: Dict[Tuple[Optional[int], str], CachedPage] = {}
        self._versions: Dict[Optional[int], int] = {}

    def _version(self, tenant_id: Optional[int]) -> int:
        return self._versions.get(tenant_id, 0)

    def get(self, tenant_id: Optional[int], key: str) -> Optional[CachedPage]:
        """The live entry for this key, or ``None`` when absent/stale/invalidated."""
        entry = self._entries.get((tenant_id, key))
        if entry is None:
            return None
        if entry.version != self._version(tenant_id):
            self._entries.pop((tenant_id, key), None)
            return None
        if (time.monotonic() - entry.stored_at) > self.ttl_seconds:
            self._entries.pop((tenant_id, key), None)
            return None
        return entry

    def put(self, tenant_id: Optional[int], key: str, body: str) -> CachedPage:
        """Store ``body`` under this key and return the entry (with its ETag)."""
        entry = CachedPage(
            body=body,
            etag='"' + hashlib.sha256(body.encode('utf-8')).hexdigest()[:32] + '"',
            stored_at=time.monotonic(),
            version=self._version(tenant_id),
        )
        self._entries[(tenant_id, key)] = entry
        while len(self._entries) > self.max_entries:
            self._entries.pop(next(iter(self._entries)), None)
        return entry

    def invalidate_tenant(self, tenant_id: Optional[int]) -> None:
        """Mark every entry for one tenant stale.

        A version bump rather than a scan: this runs from a sync event-bus
        subscriber inside ``publish``, which must not do real work.
        """
        self._versions[tenant_id] = self._version(tenant_id) + 1

    def clear(self) -> None:
        self._entries.clear()
        self._versions.clear()
