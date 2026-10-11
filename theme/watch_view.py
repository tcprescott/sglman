"""The static Watch page: where a stranger from a tweet or a QR code lands.

A pure renderer for ``GET /live`` (``pages/static_watch.py``): every stage's
stream link with what is on it now and next, the published brackets, and the
way in for someone who wants to commentate or track. Plain HTML on the static
bracket shell, so a crowd costs no websocket and the app's tab-admission budget
(docs/scaling-roadmap.md) is left to the people running the event.

Every piece of user-controlled text goes through ``_esc``; stream URLs also pass
``http_url_or_empty`` so a pre-validation ``javascript:`` row draws no link.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from application.utils.safe_url import http_url_or_empty
from theme.brackets.static_view.document import _bar, _document
from theme.brackets.static_view.markup import _esc, _tag

#: Upcoming matches listed per stage. The page answers "what's on and what's
#: next", not "the whole day": the rest of the day is a sign-in away.
UP_NEXT_LIMIT = 3


@dataclass
class WatchMatch:
    """One match row, already formatted on the community's clock."""

    time: str
    tournament: str
    #: ``None`` when staff haven't made today's names public.
    players: Optional[str] = None


@dataclass
class WatchStage:
    name: str
    stream_url: str = ''
    on_now: List[WatchMatch] = field(default_factory=list)
    up_next: List[WatchMatch] = field(default_factory=list)


@dataclass
class WatchView:
    community: str
    stages: List[WatchStage] = field(default_factory=list)
    #: ``(tournament_id, name)`` for each tournament with a published stage.
    tournaments: List[Tuple[int, str]] = field(default_factory=list)
    timezone_label: str = ''
    event_info: bool = False
    crew_signup_path: str = '/login'
    root_path: str = ''
    primary_color: Optional[str] = None
    generated_at: Optional[datetime] = None
    refresh_seconds: int = 60


_WATCH_CSS = """
<style>
.wizw-stage-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  justify-content: space-between; margin-bottom: 8px; }
.wizw-stage-name { font-size: 1.15rem; font-weight: 700; }
.wizw-watch { display: inline-block; padding: 10px 16px; border-radius: 6px;
  background: var(--wiz-header-bg, #9C6B12); color: #fff !important;
  font-weight: 600; text-decoration: none; }
.wizw-label { font-size: .72rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--bracket-muted, #6b7280); margin: 10px 0 4px; }
.wizw-row { display: flex; gap: 10px; align-items: baseline; padding: 4px 0;
  border-top: 1px solid var(--bracket-card-border, #e2e5ea); }
.wizw-time { font-variant-numeric: tabular-nums; font-size: .85rem; min-width: 4.5em; }
.wizw-main { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.wizw-live { display: inline-block; border-radius: 10px; padding: 1px 8px;
  font-size: .7rem; font-weight: 700; background: #B3362B; color: #fff; }
.wizw-links a { display: block; padding: 8px 0; font-weight: 600; }
</style>
"""


def _match_row(match: WatchMatch, *, live: bool) -> str:
    who = match.players if match.players else match.tournament
    sub = _tag('div', 'wizs-sub', _esc(match.tournament)) if match.players and match.tournament else ''
    lead = _tag('span', 'wizw-live', 'LIVE') if live else _esc(match.time)
    return _tag(
        'div', 'wizw-row',
        _tag('div', 'wizw-time', lead)
        + _tag('div', 'wizw-main', _tag('div', '', _esc(who)) + sub),
    )


def _stage_card(stage: WatchStage) -> str:
    url = http_url_or_empty(stage.stream_url)
    head = _tag('div', 'wizw-stage-name', _esc(stage.name))
    if url:
        head += (
            f'<a class="wizw-watch" href="{_esc(url)}" target="_blank" '
            f'rel="noopener noreferrer">Watch stream</a>'
        )
    inner = _tag('div', 'wizw-stage-head', head)
    if stage.on_now:
        inner += _tag('div', 'wizw-label', 'On now')
        inner += ''.join(_match_row(m, live=True) for m in stage.on_now)
    if stage.up_next:
        inner += _tag('div', 'wizw-label', 'Up next')
        inner += ''.join(_match_row(m, live=False) for m in stage.up_next)
    if not stage.on_now and not stage.up_next:
        inner += _tag('div', 'wizs-muted', 'Nothing else on this stage today.')
    return _tag('div', 'wizs-card', inner)


def render_watch_document(view: WatchView) -> str:
    root = view.root_path
    parts: List[str] = []

    if view.stages:
        parts.extend(_stage_card(s) for s in view.stages)
    else:
        parts.append(_tag(
            'div', 'wizs-card',
            _tag('div', 'wizs-muted', 'Nothing is on a stream right now. Check back later.'),
        ))

    if view.tournaments:
        links = ''.join(
            f'<a href="{_esc(root)}/live/tournament/{_esc(tid)}/brackets">{_esc(name)}</a>'
            for tid, name in view.tournaments
        )
        parts.append(_tag(
            'div', 'wizs-card',
            _tag('div', 'wizs-title', 'Brackets') + _tag('div', 'wizw-links', links),
        ))

    more = (
        f'<a href="{_esc(root)}{_esc(view.crew_signup_path)}">'
        'Commentate or track a match</a>'
    )
    if view.event_info:
        more += f'<a href="{_esc(root)}/event-info">Event information</a>'
    more += f'<a href="{_esc(root)}/help">How it works</a>'
    parts.append(_tag(
        'div', 'wizs-card',
        _tag('div', 'wizs-title', 'Get involved') + _tag('div', 'wizw-links', more),
    ))

    zone = f'Times in {view.timezone_label}' if view.timezone_label else ''
    return _document(
        title=f'Watch — {view.community}',
        description=f'{view.community}: stream links and what’s on now',
        body=_WATCH_CSS + _bar(view.community, _esc(zone)) + _tag('div', 'wizs-wrap', ''.join(parts)),
        refresh_seconds=view.refresh_seconds,
        primary_color=view.primary_color,
        generated_at=view.generated_at,
    )
