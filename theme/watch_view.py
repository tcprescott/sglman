"""The Watch page's content, and its static rendering.

``/live`` is where someone from a tweet, a stream overlay or a QR code lands:
every stage's stream with what is on it now and next, what's coming up on
stream over the next few days, and every tournament's bracket. The same
:class:`WatchView` feeds both renderings: the live NiceGUI page
(``theme/watch_live.py``) and the plain HTML one here, which the page falls
back to when a crowd arrives faster than the app can admit live viewers
(``pages/static_watch.py``).

The static rendering updates itself in place rather than reloading, so a
viewer's Twitch player keeps playing: a small script refetches the page and
swaps the ``#wizw-live`` block. The player is built in the browser from
``location.hostname``, the ``parent`` Twitch insists on, so one cached render
serves every host the community answers on.

Every piece of user-controlled text goes through ``_esc``; links also pass
``http_url_or_empty`` so a pre-validation ``javascript:`` row draws no link.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from application.utils.safe_url import http_url_or_empty
from theme.brackets.static_view.document import _document
from theme.brackets.static_view.markup import _esc, _tag

#: Upcoming matches listed under each stage; the rest are in "Coming up".
UP_NEXT_LIMIT = 3
#: Rows in "Coming up on stream", across every stage and day.
COMING_UP_LIMIT = 12
#: How often the static rendering refetches itself.
STATIC_REFRESH_SECONDS = 60

#: Stands in for the "Get involved" section until its content is settled.
GET_INVOLVED_PLACEHOLDER = 'Ways to help out are coming soon.'


@dataclass
class WatchMatch:
    """One match, already formatted on the community's clock."""

    time: str
    players: str
    tournament: str = ''
    stage: str = ''
    commentators: str = ''
    trackers: str = ''
    match_id: int = 0
    tournament_id: Optional[int] = None


@dataclass
class WatchStage:
    id: int
    name: str
    stream_url: str = ''
    #: The Twitch channel ``stream_url`` points at, when it is one.
    channel: Optional[str] = None
    on_now: Optional[WatchMatch] = None
    up_next: List[WatchMatch] = field(default_factory=list)


@dataclass
class WatchDay:
    label: str
    matches: List[WatchMatch] = field(default_factory=list)


@dataclass
class WatchTournament:
    id: int
    name: str
    format: str = ''
    #: How far along its bracket is, for a spectator; '' when nothing says.
    status: str = ''
    #: ``wiz-chip--<tone>``: live, ok, pending or neutral.
    tone: str = 'neutral'
    #: Absolute (Challonge, or another site) or root-relative (``/live/...``).
    bracket_url: str = ''
    rules_url: str = ''


@dataclass
class WatchView:
    community: str
    stages: List[WatchStage] = field(default_factory=list)
    coming: List[WatchDay] = field(default_factory=list)
    tournaments: List[WatchTournament] = field(default_factory=list)
    timezone_label: str = ''
    primary_color: Optional[str] = None
    generated_at: Optional[datetime] = None


def bracket_href(url: str, root_path: str) -> str:
    """Where a tournament's bracket link goes, tenant prefix applied."""
    if url.startswith('/'):
        return f'{root_path}{url}'
    return http_url_or_empty(url)


# Only what the live page gets from Quasar: the shared .wiz-watch-* rules
# live in styles.css, which the static shell loads too.
_WATCH_CSS = """
<style>
body { --wiz-header-height: 0px; }
.wizw-stack { display: flex; flex-direction: column; gap: 16px; }
.wizw-stack > .wizs-card, .wiz-watch-two > .wizs-card { margin: 0; }
.wizw-btn { display: inline-flex; align-items: center; justify-content: center;
  min-height: 36px; padding: 0 12px; border-radius: 8px; font: inherit; font-weight: 700;
  border: 1px solid var(--wiz-header-bg, #9C6B12); background: transparent;
  color: var(--wiz-link, #855B0F); cursor: pointer; text-decoration: none; flex: none; }
.wizw-btn[aria-pressed="true"] { background: var(--wiz-header-bg, #9C6B12); color: #fff; }
.wizw-theater { display: none; }
.wizw-theater.is-open { display: grid; }
.timeline-container .match-card { background: var(--surface, #fff); border-radius: 8px;
  display: flex; flex-direction: column; }
.stage-header { display: flex; justify-content: space-between; }
.match-card-top { display: flex; align-items: center; gap: 8px; }
.wizw-bar-end { display: flex; align-items: center; gap: 10px; }
.wizw-theme { width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border-subtle, #e2e1de);
  background: transparent; color: inherit; font-size: 24px; line-height: 1; cursor: pointer; }
</style>
"""

# Builds the player in the browser (``parent`` must be the host the reader
# reached, which one shared render cannot know), and refetches the page every
# STATIC_REFRESH_SECONDS to swap #wizw-live without touching the player.
_WATCH_JS = """
<script>(function(){
var theater=document.getElementById('wizw-theater');
var frame=document.getElementById('wizw-frame');
var watching=null;
function pick(id){return document.querySelector('[data-watch="'+id+'"]');}
function paint(){
  var bs=document.querySelectorAll('[data-watch]');
  for(var i=0;i<bs.length;i++){var on=bs[i].getAttribute('data-watch')===watching;
    bs[i].setAttribute('aria-pressed',on?'true':'false');bs[i].textContent=on?'Watching':'Watch';}
  if(!watching)return;var b=pick(watching);if(!b)return;
  var f=['stage','time','players','tournament'];
  for(var j=0;j<f.length;j++){var el=document.getElementById('wizw-np-'+f[j]);
    if(el)el.textContent=b.getAttribute('data-'+f[j])||'';}
  var link=document.getElementById('wizw-np-link');if(link)link.href=b.getAttribute('data-url')||'#';
}
function watch(b){
  var ch=b.getAttribute('data-channel');if(!ch)return;
  watching=b.getAttribute('data-watch');
  var src='https://player.twitch.tv/?channel='+encodeURIComponent(ch)+'&parent='
    +encodeURIComponent(location.hostname)+'&autoplay=true&muted=true';
  if(frame.getAttribute('data-channel')!==ch){
    frame.innerHTML='';var f=document.createElement('iframe');f.src=src;
    f.title=(b.getAttribute('data-stage')||'')+' live stream';
    f.allow='autoplay; fullscreen; picture-in-picture';f.allowFullscreen=true;
    frame.appendChild(f);frame.setAttribute('data-channel',ch);}
  theater.classList.add('is-open');paint();
}
function close(){watching=null;frame.innerHTML='';frame.removeAttribute('data-channel');
  theater.classList.remove('is-open');paint();}
document.addEventListener('click',function(e){
  var b=e.target.closest?e.target.closest('[data-watch]'):null;
  if(b){e.preventDefault();watch(b);return;}
  if(e.target.closest&&e.target.closest('#wizw-close')){e.preventDefault();close();}
  if(e.target.closest&&e.target.closest('#wizw-theme')){
    var dark=!document.body.classList.contains('body--dark');
    document.body.classList.toggle('body--dark',dark);
    document.cookie='wiz_dark='+(dark?1:0)+'; path=/; max-age=31536000; samesite=lax';}
});
var url=document.body.getAttribute('data-refresh-url');
if(url){setInterval(function(){
  fetch(url,{cache:'no-cache',credentials:'omit'}).then(function(r){return r.ok?r.text():null;})
  .then(function(html){if(!html)return;
    var fresh=new DOMParser().parseFromString(html,'text/html');
    var next=fresh.getElementById('wizw-live');var cur=document.getElementById('wizw-live');
    if(next&&cur){cur.replaceWith(document.importNode(next,true));paint();}
    var stamp=fresh.getElementById('wizw-stamp');var old=document.getElementById('wizw-stamp');
    if(stamp&&old)old.textContent=stamp.textContent;
  }).catch(function(){});
},%d);}
})();</script>
"""


def _crew_line(label: str, names: str) -> str:
    if not names:
        return ''
    return _tag('div', 'wizs-muted', f'{_esc(label)}: {_esc(names)}')


def _match_card(match: WatchMatch, *, live: bool) -> str:
    chip = (
        '<span class="wiz-chip wiz-chip--live">On now</span>' if live
        else '<span class="wiz-chip wiz-chip--neutral">Scheduled</span>'
    )
    top = _tag('div', 'match-card-top', _tag('span', 'match-time', _esc(match.time)) + chip)
    body = top + _tag('div', 'match-players', _esc(match.players))
    if match.tournament:
        body += _tag('div', 'match-tournament', _esc(match.tournament))
    body += _crew_line('Commentary', match.commentators)
    body += _crew_line('Tracking', match.trackers)
    return _tag('div', 'match-card', body)


def _stage_card(stage: WatchStage) -> str:
    url = http_url_or_empty(stage.stream_url)
    head = _tag('div', 'stage-title', _tag('div', 'stage-name', _esc(stage.name)))
    if stage.channel:
        now = stage.on_now
        head += (
            f'<button type="button" class="wizw-btn" aria-pressed="false"'
            f' data-watch="{_esc(stage.id)}" data-channel="{_esc(stage.channel)}"'
            f' data-stage="{_esc(stage.name)}" data-url="{_esc(url)}"'
            f' data-time="{_esc(now.time if now else "")}"'
            f' data-players="{_esc(now.players if now else "Nothing on right now")}"'
            f' data-tournament="{_esc(now.tournament if now else "")}">Watch</button>'
        )
    elif url:
        head += (
            f'<a class="stage-link" href="{_esc(url)}" target="_blank" '
            f'rel="noopener noreferrer">Open stream ↗</a>'
        )
    inner = _tag('div', 'stage-header', head)
    cards = ''
    if stage.on_now:
        cards += _match_card(stage.on_now, live=True)
    cards += ''.join(_match_card(m, live=False) for m in stage.up_next)
    if not cards:
        cards = _tag('div', 'wizs-muted', 'Nothing else on this stage today.')
    inner += _tag('div', 'column-spacing wizw-stack', cards)
    return _tag('div', 'card-full-width wizs-card', inner)


def _coming(view: WatchView) -> str:
    body = _tag('h2', 'wiz-watch__h2', 'Coming up on stream')
    if not view.coming:
        return _tag('div', 'wizs-card', body + _tag('div', 'wizs-muted', 'Nothing else is scheduled on stream yet.'))
    for day in view.coming:
        body += _tag('div', 'wiz-watch-day', _esc(day.label))
        for m in day.matches:
            body += _tag(
                'div', 'wiz-watch-row',
                _tag('span', 'match-time', _esc(m.time))
                + _tag('div', 'wiz-watch-row__main',
                       _tag('div', 'wiz-watch-row__players', _esc(m.players))
                       + _tag('div', 'wizs-muted', _esc(m.tournament)))
                + _tag('span', 'wiz-watch-tag', _esc(m.stage)),
            )
    return _tag('div', 'wizs-card', body)


def _tournaments(view: WatchView, root: str) -> str:
    body = _tag('h2', 'wiz-watch__h2', 'Tournaments')
    if not view.tournaments:
        return _tag('div', 'wizs-card', body + _tag('div', 'wizs-muted', 'No brackets are up yet.'))
    for t in view.tournaments:
        line = _tag('span', 'wiz-watch-row__players', _esc(t.name))
        if t.status:
            line += f'<span class="wiz-chip wiz-chip--{_esc(t.tone)}">{_esc(t.status)}</span>'
        links = ''
        href = bracket_href(t.bracket_url, root)
        if href:
            links += f'<a href="{_esc(href)}" target="_blank" rel="noopener noreferrer">Bracket ↗</a>'
        rules = http_url_or_empty(t.rules_url)
        if rules:
            links += f'<a href="{_esc(rules)}" target="_blank" rel="noopener noreferrer">Rules ↗</a>'
        body += _tag(
            'div', 'wiz-watch-tourn',
            _tag('div', 'wiz-watch-tourn__line', line)
            + (_tag('div', 'wizs-muted', _esc(t.format)) if t.format else '')
            + (_tag('div', 'wiz-watch-links', links) if links else ''),
        )
    return _tag('div', 'wizs-card', body)


_THEME_BUTTON = (
    '<button type="button" id="wizw-theme" class="wizw-theme" '
    'aria-label="Toggle dark mode" title="Toggle dark mode">\u25d0</button>'
)

_THEATER = (
    '<section id="wizw-theater" class="twitch-theater wizw-theater" aria-label="Live stream">'
    '<div id="wizw-frame" class="twitch-theater__player"></div>'
    '<aside class="twitch-theater__panel">'
    '<div class="twitch-theater__eyebrow">Now watching · <span id="wizw-np-stage"></span></div>'
    '<div class="twitch-theater__now"><span id="wizw-np-time" class="match-time"></span> '
    '<span class="wiz-chip wiz-chip--live">On now</span></div>'
    '<div id="wizw-np-players" class="twitch-theater__players"></div>'
    '<div id="wizw-np-tournament" class="twitch-theater__tournament"></div>'
    '<div class="twitch-theater__actions wiz-watch-links">'
    '<a id="wizw-np-link" href="#" target="_blank" rel="noopener noreferrer">Open on Twitch ↗</a>'
    '<button id="wizw-close" type="button" class="wizw-btn">Close player</button>'
    '</div></aside></section>'
)


def render_watch_document(view: WatchView, *, root_path: str = '', refresh_url: str = '') -> str:
    """The whole static Watch page. ``refresh_url`` is what it refetches itself from."""
    stages = (
        _tag('div', 'timeline-container', ''.join(_stage_card(s) for s in view.stages))
        if view.stages else
        _tag('div', 'wizs-card', _tag('div', 'wizs-muted', 'Nothing is on a stream right now. Check back later.'))
    )
    live = _tag(
        'div', 'wizw-stack',
        _tag('h2', 'wiz-watch__h2', 'On stream today') + stages
        + _tag('div', 'wiz-watch-two', _coming(view) + _tournaments(view, root_path)),
    )
    involved = _tag(
        'div', 'wizs-card',
        _tag('h2', 'wiz-watch__h2', 'Get involved') + _tag('div', 'wizs-muted', GET_INVOLVED_PLACEHOLDER),
    )
    zone = f'Times in {view.timezone_label}' if view.timezone_label else ''
    body = (
        _WATCH_CSS
        + _tag(
            'div', 'wizs-bar',
            _tag('div', 'wizs-brand', _esc(view.community))
            + _tag('div', 'wizw-bar-end', _tag('span', 'wizs-sub', _esc(zone)) + _THEME_BUTTON),
        )
        + _tag(
            'div', 'wizs-wrap wizw-stack',
            _THEATER + f'<div id="wizw-live">{live}</div>' + involved,
        )
        + (_WATCH_JS % (STATIC_REFRESH_SECONDS * 1000))
    )
    document = _document(
        title=f'Watch — {view.community}',
        description=f'{view.community}: streams, what’s on now and the brackets',
        body=body,
        refresh_seconds=0,
        primary_color=view.primary_color,
        generated_at=view.generated_at,
        footer_links=f'updates itself every {STATIC_REFRESH_SECONDS}s',
    )
    document = document.replace('<div class="wizs-foot">', '<div class="wizs-foot" id="wizw-stamp">', 1)
    if refresh_url:
        document = document.replace('<body>', f'<body data-refresh-url="{_esc(refresh_url)}">', 1)
    return document
