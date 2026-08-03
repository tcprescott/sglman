"""Pure builders for in-app route paths.

Section slugs are path segments (``/admin/schedule``, ``/home/player``); anything
a surface needs to focus on — or a dialog it should open on arrival — travels as a
query param. Root-relative on purpose: NiceGUI derives the client prefix from the
page's ``root_path``, so a bare ``/admin/…`` resolves inside ``/t/<slug>``.

Lives in ``utils`` rather than ``pages/`` because the notification layer needs the
same paths: a DM's "Pick a time" button and the page's own link must address the
identical route, and a service may not import a presentation module.
``pages/admin_tabs/links.py`` re-exports the admin half for its existing callers.
"""

from datetime import date, datetime
from typing import Optional
from urllib.parse import urlencode

# Admin tab slugs (theme.base.tab_slug of each tab's label).
SCHEDULE = 'schedule'
REPORTS = 'reports'
VOL_SCHEDULE = 'vol-schedule'
CHALLONGE = 'challonge'
USERS = 'users'

# Home tab slugs.
HOME_PLAYER = 'player'
HOME_SCHEDULE = 'schedule'
HOME_MY_CREW = 'my-crew'
HOME_TOURNAMENTS = 'tournaments'


def _query(params: dict) -> str:
    """``?a=1&b=2``, dropping empty values; '' when nothing survives.

    ``None`` and ``''`` are omitted entirely (an absent filter is not the same as
    a blank one), and dates are normalised to ISO so a caller can pass the
    ``date`` it already has.
    """
    payload: dict = {}
    for key, value in params.items():
        if value is None or value == '':
            continue
        payload[key] = value.isoformat() if isinstance(value, (date, datetime)) else value
    return f'?{urlencode(payload)}' if payload else ''


def admin_url(section: Optional[str] = None, **params) -> str:
    """Build ``/admin[/<section>][?…]``, dropping empty params."""
    return f"{'/admin/' + section if section else '/admin'}{_query(params)}"


def home_url(section: Optional[str] = None, **params) -> str:
    """Build ``/home[/<section>][?…]``, dropping empty params."""
    return f"{'/home/' + section if section else '/home'}{_query(params)}"


def player_schedule_url(bracket_match_id: int) -> str:
    """The Player tab with the schedule dialog for one bracket matchup open.

    The entrant's *only* route to booking a bracket game: the public bracket page
    gates its Schedule button behind ``is_staff``, so a DM that sent a player
    there left them at a dialog whose sole button was Close.
    """
    return home_url(HOME_PLAYER, schedule=bracket_match_id)


def player_match_url(match_id: int) -> str:
    """The Player tab narrowed to one match.

    Where the stage DMs land: the player's own board, showing the match the
    message is about and nothing else. ``/admin/schedule?match_id=…`` is the
    staff equivalent and no use here, because a player cannot open the admin
    board at all.
    """
    return home_url(HOME_PLAYER, match=match_id)


def player_reschedule_url(match_id: int) -> str:
    """The Player tab with the reschedule-request dialog for one match open.

    Where a declined request ends: "ask again with a different time" is a real
    next step, so the DM's button opens the form rather than the tab.
    """
    return home_url(HOME_PLAYER, reschedule=match_id)


def admin_reschedule_request_url(request_id: int) -> str:
    """The admin Schedule board with one request's decision dialog open.

    Not the board filtered to the match: staff opening this have been asked to
    decide, and the reason and proposed time live in the dialog. Landing them on
    a row they must then find and click is the failure the link rules name.
    """
    return admin_url(SCHEDULE, reschedule_request=request_id)
