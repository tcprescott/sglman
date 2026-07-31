"""URLs into the admin tabs.

Section slugs are path segments (``/admin/schedule``); everything a surface
needs to focus on arrives as a query param, the same way the Reports tab has
always taken its filters. Root-relative on purpose: NiceGUI derives the client
prefix from the page's root_path, so a bare ``/admin/…`` resolves inside
``/t/<slug>`` — see middleware/tenant.py.

Slugs are what ``theme.base.tab_slug`` derives from each tab's label, so they
are named here as constants rather than spelled out at call sites.
"""

from datetime import date, datetime
from typing import Optional
from urllib.parse import urlencode

SCHEDULE = 'schedule'
REPORTS = 'reports'
VOL_SCHEDULE = 'vol-schedule'
CHALLONGE = 'challonge'


def admin_url(section: Optional[str] = None, **params) -> str:
    """Build ``/admin[/<section>][?…]``, dropping empty params.

    ``None`` and ``''`` are omitted entirely (an absent filter is not the same
    as a blank one), and dates are normalised to ISO so a caller can pass the
    ``date`` it already has.
    """
    payload: dict = {}
    for key, value in params.items():
        if value is None or value == '':
            continue
        if isinstance(value, (date, datetime)):
            payload[key] = value.isoformat()
        else:
            payload[key] = value
    path = f'/admin/{section}' if section else '/admin'
    return f'{path}?{urlencode(payload)}' if payload else path
