"""Request-time display-timezone context — the primitive every rendered time reads.

Datetimes are stored UTC everywhere. *Which* wall clock a human sees them on is a
presentation concern that varies per viewer, so — exactly like the tenant id — it
is resolved once per page build and stashed in a :class:`~contextvars.ContextVar`
rather than threaded through every formatting call.

**Resolution is async and does DB reads; reading it back is sync and free.** The
resolver (:func:`application.services.TimezoneService.resolve`) runs once at page
build, where the tenant and the signed-in user are already loaded, and writes the
*answer* — a plain IANA name — here. ``application/utils/timezone.py`` then reads
it synchronously from ~390 formatting call sites at no cost.

**Why a contextvar and a fallback.** Same two-tier shape as
``application/tenant_context.py``, and for the same reason: the HTTP middleware
and the page builder only see the initial load. Once NiceGUI's websocket takes
over, every UI event handler runs *outside* any request and the contextvar is
gone. So resolution reads:

1. the contextvar (set at page build, and by :func:`tz_scope` for background code); else
2. the current NiceGUI client's per-connection stash (``app.storage.client['tz']``); else
3. nothing — and the caller falls back to :data:`FALLBACK_TIMEZONE`.

Anything running with neither — the Discord bot loop, workers, ``background_tasks``,
and every **shared-output** surface (cached spectator pages, channel-wide posts) —
must either bind a tz explicitly with :func:`tz_scope` or render in the tenant's
own timezone. A shared artifact must never inherit one viewer's clock.

This module is a peer of ``application/services`` (like ``application/events`` and
``application/tenant_context``) and is import-safe from every layer. It lazy-imports
NiceGUI only inside the fallback so it stays usable with no UI context.
"""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The zone used when nothing else resolves: no tenant, no user, no browser hint.
# Matches the app's historical hardcoded zone so an unresolvable context renders
# exactly as it did before timezones became dynamic.
FALLBACK_TIMEZONE = 'America/New_York'

# Cookie the browser-side detector writes with the device's IANA zone. Read by
# ``TimezoneService.resolve`` as the lowest-priority signal, and only when the
# tenant leaves the choice to the user and the user has set no preference.
TZ_COOKIE = 'wiz_tz'

# None means "unresolved" — read back as FALLBACK_TIMEZONE by current_timezone_name().
_tz_var: ContextVar[Optional[str]] = ContextVar('wizzrobe_display_tz', default=None)

# The zone the *browser* reported for this request, read from the TZ_COOKIE by
# ``TenantMiddleware``. Kept separate from the resolved zone above because it is
# an input to resolution, not its answer: a pinned community ignores it entirely,
# and a user with a saved preference outranks it.
_browser_tz_var: ContextVar[Optional[str]] = ContextVar('wizzrobe_browser_tz', default=None)

# ZoneInfo construction hits the filesystem; the set of live zones per process is
# tiny (one per tenant/user in play), so cache them. ZoneInfo is immutable and
# thread-safe, and ZoneInfo itself caches too — this also memoizes the *failures*,
# which is what keeps a bad stored name from stat-ing the tzdata tree per render.
_zone_cache: dict[str, ZoneInfo] = {}


def is_valid_timezone(name: Optional[str]) -> bool:
    """Whether ``name`` is a zone this system's tzdata can actually load.

    The validation gate for anything user- or admin-supplied. Names are stored as
    plain strings (a tenant config blob, a user column, a cookie), so every read
    path is defensive: an unknown zone degrades to the fallback rather than
    raising mid-render.
    """
    if not name or not isinstance(name, str):
        return False
    try:
        get_zone(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False


def get_zone(name: str) -> ZoneInfo:
    """A cached :class:`ZoneInfo` for ``name``. Raises if tzdata has no such zone."""
    zone = _zone_cache.get(name)
    if zone is None:
        zone = ZoneInfo(name)
        _zone_cache[name] = zone
    return zone


def set_timezone_name(name: Optional[str]) -> Token:
    """Bind the ambient display zone, returning a token for :func:`reset_timezone_name`."""
    return _tz_var.set(name)


def reset_timezone_name(token: Token) -> None:
    """Restore the zone the matching :func:`set_timezone_name` replaced."""
    _tz_var.reset(token)


def set_browser_timezone(name: Optional[str]) -> Token:
    """Record the zone the browser reported, returning a token to reset it."""
    return _browser_tz_var.set(name)


def reset_browser_timezone(token: Token) -> None:
    """Restore the browser zone the matching :func:`set_browser_timezone` replaced."""
    _browser_tz_var.reset(token)


def get_browser_timezone() -> Optional[str]:
    """The zone the browser reported for this request, if any.

    Contextvar first (set per HTTP request from the cookie), then the per-client
    stash, so a websocket handler re-resolving a zone mid-connection still sees
    the device's own zone rather than dropping to the community default.
    """
    name = _browser_tz_var.get()
    if name is not None:
        return name
    try:
        from nicegui import app
    except Exception:
        return None
    try:
        return app.storage.client.get('browser_tz')
    except Exception:
        return None


def stash_client_browser_timezone(name: Optional[str]) -> None:
    """Persist the browser-reported zone onto the current NiceGUI client."""
    try:
        from nicegui import app
    except Exception:
        return
    try:
        app.storage.client['browser_tz'] = name
    except Exception:
        pass


def _client_stash_timezone() -> Optional[str]:
    """The zone stashed on the current NiceGUI client, or None.

    Fully defensive, like ``tenant_context._client_stash_tenant_id``: returns None
    whenever NiceGUI is unavailable or there is no active client context (tests,
    workers, the bot loop), so resolution never raises just because the UI layer
    is absent.
    """
    try:
        from nicegui import app
    except Exception:
        return None
    try:
        return app.storage.client.get('tz')
    except Exception:
        # app.storage.client raises when accessed outside a client/slot context.
        return None


def get_current_timezone_name() -> Optional[str]:
    """The resolved display zone, or None: contextvar first, then client stash."""
    name = _tz_var.get()
    if name is not None:
        return name
    return _client_stash_timezone()


def current_timezone_name() -> str:
    """The display zone to render in — always a usable IANA name.

    Never raises and never returns None: an unresolved or unloadable zone becomes
    :data:`FALLBACK_TIMEZONE`. Formatting a timestamp must not be able to fail,
    so this is deliberately total.
    """
    name = get_current_timezone_name()
    if is_valid_timezone(name):
        return name
    return FALLBACK_TIMEZONE


def current_timezone() -> ZoneInfo:
    """The resolved display zone as a :class:`ZoneInfo`."""
    return get_zone(current_timezone_name())


def stash_client_timezone(name: Optional[str]) -> None:
    """Persist the resolved zone onto the current NiceGUI client (page-build time).

    Read back by :func:`get_current_timezone_name` when a websocket UI event
    handler runs with the contextvar unset. No-op when there is no client context.
    Unlike the tenant stash this **does** write on every page build including the
    fallback value, because a connection's viewer can change zone (a re-login as
    someone else, an admin flipping the tenant pin) and a stale stash would
    outlive the change for the life of the connection.
    """
    try:
        from nicegui import app
    except Exception:
        return
    try:
        app.storage.client['tz'] = name
    except Exception:
        pass


@contextmanager
def tz_scope(name: Optional[str]) -> Iterator[None]:
    """Bind ``name`` as the ambient display zone for the duration of the block.

    Safe inside ``async`` code for the same reason :func:`tenant_scope` is: the
    contextvar is set/reset synchronously around the ``yield`` and propagates
    across ``await`` within the task.

    Use it wherever output is **not** for the current request's viewer:

    - a worker or bot rendering for a specific recipient → that recipient's zone
    - a cached or shared artifact (spectator brackets, a channel post) → the
      tenant's zone, via ``TimezoneService.tenant_timezone_name``

    Passing ``None`` deliberately unbinds, restoring fallback behaviour.
    """
    token = _tz_var.set(name)
    try:
        yield
    finally:
        _tz_var.reset(token)
