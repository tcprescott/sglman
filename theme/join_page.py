"""The door beside the membership gate.

A non-member reaching a tenant page gets this rather than a 403. The distinction
matters: forbidden-by-role is a dead end, but not-a-member is a state with a
remedy, and the page whose whole job is to offer that remedy should not open by
telling you no.

It is also the community's whole first impression, so it carries two previews of
what is behind the gate: the published brackets (already world-readable, just
unreachable without the URL) and — only where staff turned it on — today's match
times and player names.

Rendered synchronously into the current page context, like
:mod:`theme.error_page`, so it can be called from the middleware decorator
without restructuring it. Everything that needs an ``await`` is resolved by
:func:`resolve_join_preview` first and handed in.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from nicegui import background_tasks, context, ui

from models import JoinRequestStatus, User
from theme.base import BaseLayout

logger = logging.getLogger(__name__)

#: How many of today's matches the door lists. It is a first impression, not a
#: schedule board — a real event day runs to thirty-plus rows, which buries the
#: Request access button under a wall of names nobody outside the community can
#: act on. The rest are counted, not listed.
PREVIEW_LIMIT = 12


@dataclass
class PreviewMatch:
    """One row of the today's-matches preview, already formatted."""

    time: str
    players: str
    tournament: str


@dataclass
class JoinPreview:
    """What a non-member may see of this community, resolved and formatted."""

    #: ``(tournament_id, tournament_name)`` for each tournament with published
    #: stages. Empty when BRACKETS is off or nothing is published yet.
    tournaments: List[Tuple[int, str]] = field(default_factory=list)
    #: Today's matches, on the **community's** clock. Empty unless staff enabled
    #: the preview.
    matches: List[PreviewMatch] = field(default_factory=list)
    #: Matches today beyond the ones listed above, or 0.
    more_matches: int = 0
    #: Whether staff enabled the match preview at all — an enabled preview with
    #: no matches says "nothing today", a disabled one says nothing.
    matches_enabled: bool = False
    #: The zone the times above are in, e.g. ``EST``.
    timezone_label: str = ''


def roster_label(match) -> str:
    """Who is playing, in one line that stays one line.

    A bracket match names both players. A ten-racer play-in named all ten and
    ran off the card, so past two the rest are counted.
    """
    names = [p.user.preferred_name for p in match.players]
    if not names:
        return match.title or 'TBD'
    if len(names) <= 2:
        return ' vs '.join(names)
    return f'{names[0]} vs {names[1]} +{len(names) - 2} more'


async def resolve_join_preview(tenant_id: int) -> JoinPreview:
    """Everything the join page shows a non-member, or an empty preview.

    Never raises: this decorates the door, and a community whose bracket list or
    schedule read fails should still be able to take a join request.
    """
    from application.services import BracketService, MatchService
    from application.services.feature_flag_service import FeatureFlagService
    from application.services.system_config_service import (
        KEY_JOIN_PREVIEW,
        SystemConfigService,
    )
    from application.services.timezone_service import TimezoneService
    from application.timezone_context import tz_scope
    from application.utils.timezone import format_local_time, timezone_label, today_local
    from models import FeatureFlag
    from theme.brackets import visible_stages

    preview = JoinPreview()

    try:
        if await FeatureFlagService().is_enabled(FeatureFlag.BRACKETS):
            # Anonymous, always: a DRAFT or CANCELLED stage is unpublished, and
            # the door is read by people who hold no role here by definition.
            stages = visible_stages(
                await BracketService().list_all_brackets(), is_staff=False,
            )
            seen: dict = {}
            for stage in stages:
                seen.setdefault(
                    stage.tournament_id,  # type: ignore[attr-defined]
                    stage.tournament.name,
                )
            preview.tournaments = list(seen.items())
    except Exception:
        logger.exception('Join page: bracket preview failed for tenant %s', tenant_id)

    try:
        preview.matches_enabled = await SystemConfigService.get_bool(KEY_JOIN_PREVIEW)
        if preview.matches_enabled:
            # The community's own clock, not the visitor's: "today" here means
            # the event's day, and someone reading from two zones over must not
            # be shown a different list than the person standing in the venue.
            tz = await TimezoneService.tenant_timezone_name(tenant_id)
            with tz_scope(tz):
                preview.timezone_label = timezone_label()
                # Unfinished only: a door showing what already happened this
                # morning answers a question nobody standing outside is asking.
                matches = await MatchService().get_matches_for_date(
                    today_local(), exclude_finished=True, require_stage=False,
                )
                preview.matches = [
                    PreviewMatch(
                        time=format_local_time(match.scheduled_at),
                        players=roster_label(match),
                        tournament=match.tournament.name if match.tournament else '',
                    )
                    for match in matches[:PREVIEW_LIMIT]
                ]
                preview.more_matches = max(0, len(matches) - PREVIEW_LIMIT)
    except Exception:
        logger.exception('Join page: match preview failed for tenant %s', tenant_id)

    return preview


def _render_preview(preview: JoinPreview) -> None:
    """The two look-inside sections, beneath whatever the door is offering."""
    if not preview.tournaments and not preview.matches_enabled:
        return

    ui.separator().classes('separator-spacing')

    if preview.tournaments:
        ui.label('Brackets').classes('text-subtitle2 text-bold')
        for tournament_id, name in preview.tournaments:
            ui.button(
                name, icon='account_tree',
                on_click=lambda tid=tournament_id: ui.navigate.to(
                    f'/tournament/{tid}/brackets'
                ),
            ).props('flat dense no-caps align=left').classes('w-full')

    if not preview.matches_enabled:
        return

    label = 'Today' + (f' ({preview.timezone_label})' if preview.timezone_label else '')
    ui.label(label).classes('text-subtitle2 text-bold q-mt-md')
    if not preview.matches:
        ui.label('Nothing scheduled today.').classes('italic-note')
        return
    for match in preview.matches:
        with ui.row().classes('items-center gap-3 no-wrap w-full'):
            ui.label(match.time).classes('text-mono text-caption')
            ui.label(match.players).classes('text-body2 col ellipsis')
            if match.tournament:
                ui.label(match.tournament).classes('text-caption text-grey ellipsis')
    if preview.more_matches:
        ui.label(f'…and {preview.more_matches} more today.').classes('text-caption text-grey')


def render_join_page(
    *,
    tenant_id: int,
    tenant_name: str,
    user: Optional[User],
    pending: bool = False,
    preview: Optional[JoinPreview] = None,
) -> None:
    """Ask to join, or say the request is already in.

    ``pending`` and ``preview`` are resolved by the caller (which has already
    loaded the user), so this stays synchronous.
    """
    ui.page_title(f'{tenant_name} — Join')
    preview = preview or JoinPreview()

    try:
        BaseLayout(user=user).render_chrome()
    except Exception:  # pragma: no cover - defensive, mirroring error_page
        pass

    with ui.column().classes('error-page-container'):
        with ui.card().classes('error-card join-card'):
            ui.icon('meeting_room').props('size=xl color=primary')
            ui.label(tenant_name).classes('error-headline')

            if user is None:
                ui.label(
                    'Sign in to ask to join this community.'
                ).classes('error-message')
                ui.button('Sign in', icon='login',
                          on_click=lambda: ui.navigate.to('login')).props('color=primary')
                _render_preview(preview)
                return

            if pending:
                # Once asked, there is nothing else to offer — a second button
                # would only produce a second identical request.
                ui.label(
                    'Your request to join is with this community’s staff. '
                    'You will get a message either way.'
                ).classes('error-message')
                _render_preview(preview)
                return

            ui.label(
                'You are not a member of this community yet. Ask to join and its '
                'staff will decide.'
            ).classes('error-message')

            message = ui.textarea(
                'Anything they should know? (optional)',
            ).classes('w-full').props('maxlength=500 counter autogrow')

            async def submit(client) -> None:
                from application.services import TenantMembershipService

                with client:
                    try:
                        await TenantMembershipService().request_to_join(
                            user, tenant_id, message.value,
                        )
                    except (ValueError, PermissionError) as e:
                        ui.notify(str(e), color='warning')
                        return
                    ui.notify('Request sent.', color='positive')
                    # Re-enter the page so it re-renders in its pending state
                    # rather than leaving a button that would resubmit.
                    ui.navigate.reload()

            ui.button(
                'Request access', icon='how_to_reg',
                on_click=lambda: background_tasks.create(submit(context.client)),
            ).props('color=primary')

            _render_preview(preview)


async def resolve_join_state(user: Optional[User], tenant_id: int) -> bool:
    """Whether this user already has a pending request in this tenant."""
    if user is None:
        return False
    from application.services import TenantMembershipService

    request = await TenantMembershipService().get_request(user, tenant_id)
    return request is not None and request.status is JoinRequestStatus.PENDING
