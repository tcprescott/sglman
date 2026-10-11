"""``GET /live`` — the cached, socket-free Watch page for spectators.

The link to put in a tweet, on the stream overlay or on a QR code. It answers
the three questions someone arriving cold has (where's the stream, what's on,
what's next) without a sign-in and without a NiceGUI tab: one render per change
is shared by every reader, through the same cache, invalidation and HTTP
validators as the static bracket views in :mod:`pages.static_brackets`.

Player names follow the staff switch that already governs what a non-member
sees of today's schedule (``KEY_JOIN_PREVIEW``, Admin → System Configuration).
Stage names and stream links are shown regardless: a stream is public by nature,
and the bracket cards already link it anonymously.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import Response
from nicegui import app

from application.services import BracketService, MatchService, StageService
from application.services.feature_flag_service import FeatureFlagService
from application.services.system_config_service import KEY_JOIN_PREVIEW, SystemConfigService
from application.services.tenant_service import TenantService
from application.services.timezone_service import TimezoneService
from application.tenant_context import get_current_tenant_id
from application.timezone_context import tz_scope
from application.utils.timezone import format_local_time, timezone_label, today_local
from models import FeatureFlag
from pages.static_brackets import _cache, _conditional, _no_store, _respond, _theme_primary
from theme.join_page import roster_label
from theme.watch_view import UP_NEXT_LIMIT, WatchMatch, WatchStage, WatchView, render_watch_document

logger = logging.getLogger(__name__)

_WATCH_REFRESH_SECONDS = 60
_CACHE_KEY = 'watch'


def _row(match, show_names: bool) -> WatchMatch:
    return WatchMatch(
        time=format_local_time(match.scheduled_at) if match.scheduled_at else 'TBD',
        tournament=match.tournament.name if match.tournament else '',
        players=roster_label(match) if show_names else None,
    )


async def build_watch_view(tenant_id: int, root_path: str) -> WatchView:
    """Load everything the Watch page shows, on the community's clock."""
    show_names = await SystemConfigService.get_bool(KEY_JOIN_PREVIEW)
    tz = await TimezoneService.tenant_timezone_name(tenant_id)

    stages = sorted(await StageService().get_all_stages(active_only=True), key=lambda s: s.name)
    with tz_scope(tz):
        matches = await MatchService().get_matches_for_date(
            today_local(), exclude_finished=True, require_stage=True,
        )
        by_stage: dict[int, list] = {}
        for match in sorted(matches, key=lambda m: m.scheduled_at):
            by_stage.setdefault(match.stage_id, []).append(match)  # type: ignore[attr-defined]

        watch_stages = []
        for stage in stages:
            todays = by_stage.get(stage.id, [])
            if not stage.stream_url and not todays:
                continue
            watch_stages.append(WatchStage(
                name=stage.name,
                stream_url=stage.stream_url or '',
                # One stream shows one match. A second seated match on the same
                # stage is a result nobody recorded yet, not a second broadcast.
                on_now=[_row(m, show_names) for m in todays if m.is_seated or m.is_started][-1:],
                up_next=[
                    _row(m, show_names) for m in todays
                    if not (m.is_seated or m.is_started)
                ][:UP_NEXT_LIMIT],
            ))
        zone = timezone_label()

    tournaments: list[tuple[int, str]] = []
    live = await FeatureFlagService().enabled_flags()
    if FeatureFlag.BRACKETS in live:
        seen: dict[int, str] = {}
        # Anonymous, always: a DRAFT or CANCELLED stage is not public.
        for bracket in await BracketService().list_all_visible_brackets(None):
            seen.setdefault(bracket.tournament_id, bracket.tournament.name)
        tournaments = list(seen.items())

    return WatchView(
        community=await TenantService.current_community_name() or 'Wizzrobe',
        stages=watch_stages,
        tournaments=tournaments,
        timezone_label=zone,
        event_info=FeatureFlag.EVENT_INFO in live,
        # The board is where crew sign up; signed out, it opens the door, whose
        # Sign in button comes straight back here.
        crew_signup_path='/home/schedule',
        root_path=root_path,
        primary_color=await _theme_primary(),
        generated_at=datetime.now(timezone.utc),
        refresh_seconds=_WATCH_REFRESH_SECONDS,
    )


def create() -> None:
    """Register ``/live``. Invalidation rides on :mod:`pages.static_brackets`'s subscriber."""

    @app.api_route('/live', methods=['GET', 'HEAD'], include_in_schema=False)
    async def static_watch(request: Request) -> Response:
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return _no_store('Not found', 404)
        cached = _cache.get(tenant_id, _CACHE_KEY)
        if cached is not None:
            return _conditional(request, cached.etag, cached.body)
        view = await build_watch_view(tenant_id, request.scope.get('root_path', '') or '')
        return _respond(request, tenant_id, _CACHE_KEY, render_watch_document(view))
