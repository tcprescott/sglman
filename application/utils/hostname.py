"""Hostname normalization + effective-request-host resolution.

Host-based tenant routing compares a request's ``Host`` against each tenant's
stored ``domain``. For that comparison to be reliable, both ends must be reduced
to one canonical form: the **same** normalization is applied at write-time (when
a super-admin sets ``Tenant.domain`` on ``/platform``) and at resolution-time
(when ``TenantMiddleware`` reads the incoming host). :func:`normalize_hostname`
is that single contract; storing ``https://Foo.GG/`` and matching a browser's
``Host: foo.gg`` only works because both collapse to ``foo.gg`` here.

Kept dependency-light (only :func:`env_flag`) so it is import-safe from the
middleware, services, and presentation layers alike.
"""

import re
from typing import Mapping, Optional

from application.utils.environment import env_flag

# One DNS label: 1-63 chars, alnum, internal hyphens allowed.
_LABEL = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
_HOSTNAME_RE = re.compile(rf'^{_LABEL}(?:\.{_LABEL})*$')

# Ports the browser omits from Host, so a normalized production domain is bare.
_DEFAULT_PORTS = frozenset({'80', '443'})


def normalize_hostname(value: Optional[str]) -> Optional[str]:
    """Reduce a host/domain to canonical comparison form, or ``None`` if invalid.

    Lowercases; strips surrounding whitespace, a leading scheme, any userinfo,
    and any path/query/fragment (so ``https://foo.gg/x`` → ``foo.gg``); strips a
    fully-qualified trailing dot; drops a default ``:80``/``:443`` while
    preserving any other port (``foo.localhost:8000`` stays, for dev); IDNA /
    punycode-encodes non-ascii labels; and validates the result against a
    hostname grammar. Returns ``None`` for empty or malformed input rather than a
    best-effort guess, so a bad value fails loudly at write-time instead of
    silently never routing.
    """
    if not value:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if '://' in v:
        v = v.split('://', 1)[1]
    # Trim path / query / fragment, then any userinfo.
    v = v.split('/', 1)[0].split('?', 1)[0].split('#', 1)[0]
    if '@' in v:
        v = v.rsplit('@', 1)[1]
    if not v:
        return None
    # Split host / port (IPv6 literals are unsupported for custom domains).
    host, sep, port = v.rpartition(':')
    if not (sep and port.isdigit()):
        host, port = v, ''
    host = host.rstrip('.')
    if not host:
        return None
    try:
        host = host.encode('idna').decode('ascii')
    except (UnicodeError, ValueError):
        # The strict idna codec rejects some already-ascii hosts; leave those to
        # the regex below rather than dropping a valid ascii domain.
        pass
    if not _HOSTNAME_RE.match(host):
        return None
    if port and port not in _DEFAULT_PORTS:
        return f'{host}:{port}'
    return host


def effective_request_host(headers: Mapping[str, str]) -> Optional[str]:
    """The normalized host this request is addressed to, or ``None``.

    Uses the real ``Host`` header by default. ``X-Forwarded-Host`` is honored
    only when ``TRUST_FORWARDED_HOST`` is set — off by default because a client
    can forge it — and then only its **last** comma-separated value: the header
    is append-ordered, so the rightmost element is the one set by the nearest
    (trusted) proxy while the leftmost is client-supplied.
    """
    raw: Optional[str] = None
    if env_flag('TRUST_FORWARDED_HOST'):
        forwarded = headers.get('x-forwarded-host')
        if forwarded:
            raw = forwarded.split(',')[-1].strip()
    if not raw:
        raw = headers.get('host')
    return normalize_hostname(raw)
