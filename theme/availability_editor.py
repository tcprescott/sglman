"""Shared "My Availability" editor.

Both the player-facing home tab and the volunteer-hub tab render the same
window editor + effective-availability heatmap. This module holds the single
implementation so the two tabs stay in lockstep and the heatmap palette is
defined once (via the .avail-* token classes in styles.css).

They read their windows in opposite directions, which is what
:class:`EditorMode` carries. A volunteer **opts in**: a stretch they have not
named is no availability at all, and the shift picker skips it. A player
**opts out**: they are available for the whole event and save the times they
*cannot* play, so a stretch they have not named is a yes. That single
difference decides which statuses the dropdown offers, what a new row starts
as, and what an unfilled stretch of the heatmap means.
"""

from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

from nicegui import app, ui

from application.services import (
    SystemConfigService,
    TimezoneService,
    get_user_from_discord_id,
)
from application.timezone_context import get_zone
from application.utils.timezone import (
    format_local_date,
    format_local_time,
    parse_local_datetime,
    timezone_label,
    to_local,
)
from models import VolunteerAvailabilityStatus
from theme.dialog._helpers import native_date_input, native_time_input
from theme.help import help_icon

_STATUS_OPTIONS = {
    VolunteerAvailabilityStatus.PREFERRED.value: 'Preferred',
    VolunteerAvailabilityStatus.AVAILABLE.value: 'Available',
    VolunteerAvailabilityStatus.UNAVAILABLE.value: 'Unavailable',
}

# Resolved status -> heatmap fill class. The classes map to the phoenix
# --status-* tokens (see .avail-seg--* in styles.css) so the bar follows the
# palette and adapts to dark mode; None falls back to the neutral "empty" fill.
_STATUS_SEG_CLASS = {
    VolunteerAvailabilityStatus.UNAVAILABLE: 'avail-seg--unavailable',
    VolunteerAvailabilityStatus.PREFERRED: 'avail-seg--preferred',
    VolunteerAvailabilityStatus.AVAILABLE: 'avail-seg--available',
}
_NONE_SEG_CLASS = 'avail-seg--none'


@dataclass(frozen=True)
class EditorMode:
    """How one caller's windows are read, and the copy that follows from it."""

    status_options: Dict[str, str]
    new_row_status: VolunteerAvailabilityStatus
    empty_text: str
    precedence_text: str
    legend_statuses: Tuple[Optional[VolunteerAvailabilityStatus], ...]
    #: Grey out the hours the venue is shut. Only meaningful opt-out: with
    #: everything unblocked reading as available, an all-green 3am would
    #: promise time no match can be scheduled in.
    shade_closed_hours: bool = False
    closed_label: str = 'Outside event hours'
    new_row_times: Tuple[str, str] = ('09:00', '13:00')
    add_button_text: str = 'Add window'
    save_button_text: str = 'Save availability'

    def label(self, status) -> str:
        if status is None:
            return 'No availability'
        return self.status_options.get(status.value) or _STATUS_OPTIONS.get(
            status.value, str(status),
        )


#: Volunteers declare the windows they can work; silence means nothing.
DECLARE_MODE = EditorMode(
    status_options=_STATUS_OPTIONS,
    new_row_status=VolunteerAvailabilityStatus.AVAILABLE,
    empty_text='No availability windows yet. Add one below.',
    precedence_text='Where windows overlap, Unavailable beats Preferred beats Available.',
    legend_statuses=(
        VolunteerAvailabilityStatus.UNAVAILABLE,
        VolunteerAvailabilityStatus.PREFERRED,
        VolunteerAvailabilityStatus.AVAILABLE,
        None,
    ),
)

#: Players block out the windows they cannot play; silence means yes.
BLOCK_MODE = EditorMode(
    status_options={
        VolunteerAvailabilityStatus.UNAVAILABLE.value: "Can't play",
        VolunteerAvailabilityStatus.PREFERRED.value: 'Prefer',
    },
    new_row_status=VolunteerAvailabilityStatus.UNAVAILABLE,
    empty_text="Nothing blocked out — you count as available for the whole event.",
    precedence_text="Where windows overlap, Can't play wins.",
    add_button_text='Block out a time',
    save_button_text='Save',
    legend_statuses=(
        VolunteerAvailabilityStatus.UNAVAILABLE,
        VolunteerAvailabilityStatus.PREFERRED,
        VolunteerAvailabilityStatus.AVAILABLE,
    ),
    shade_closed_hours=True,
)


def _seg_class(status) -> str:
    return _STATUS_SEG_CLASS.get(status, _NONE_SEG_CLASS)


def _split_by_open(seg_start, seg_end, open_ranges):
    """Split a segment into ``(start, end, is_open)`` parts at the venue's hours.

    ``open_ranges`` is a sorted, non-overlapping list of instants the venue is
    open; ``None`` means no hours are configured, so everything counts as open —
    the same reading the suggestion service gives an empty hours blob.
    """
    if open_ranges is None:
        yield seg_start, seg_end, True
        return
    cursor = seg_start
    for open_start, open_end in open_ranges:
        if open_end <= cursor or open_start >= seg_end:
            continue
        if open_start > cursor:
            yield cursor, open_start, False
        part_end = min(open_end, seg_end)
        yield max(open_start, cursor), part_end, True
        cursor = part_end
    if cursor < seg_end:
        yield cursor, seg_end, False


async def _open_ranges() -> Optional[List[Tuple]]:
    """The community's operating hours as absolute instants, or ``None``.

    The hours are written on the community's clock while the graph is drawn on
    the viewer's, so they are resolved to instants here and compared as such.
    The **tenant-wide** blob, not a tournament's override: this editor is not
    about one tournament, so the venue's own hours are the only honest answer —
    which does mean a tournament that narrows its hours shades wider here than
    `MatchSuggestionService` will actually schedule.

    A day whose configured time does not exist on the clock (a DST spring
    forward) is treated as unconfigured rather than raising: every other reader
    of this blob degrades instead of failing, and shading is decoration — it
    must not take the tab down.
    """
    hours = await SystemConfigService.get_tournament_hours()
    if not hours:
        return None
    tz = get_zone(await TimezoneService.tenant_timezone_name())
    ranges = []
    for day, (open_t, close_t) in hours.items():
        try:
            ranges.append((
                parse_local_datetime(day.isoformat(), open_t.strftime('%H:%M'), tz),
                parse_local_datetime(day.isoformat(), close_t.strftime('%H:%M'), tz),
            ))
        except ValueError:
            continue
    return sorted(ranges) or None


async def render_availability_editor(
    service, *, help_text: str, help_snippet: str = '',
    title: str = 'My Availability', title_class: str = 'page-title',
    mode: EditorMode = DECLARE_MODE,
) -> None:
    """Render the availability window editor + effective-availability graph.

    ``service`` must expose ``availability_for(user)``, ``set_windows(user, ...)``
    and the static ``effective_segments(windows, start, end)`` — satisfied by both
    ``PlayerAvailabilityService`` and ``VolunteerAvailabilityService``.

    ``mode`` says whether the windows are read opt-in (``DECLARE_MODE``, the
    volunteer hub) or opt-out (``BLOCK_MODE``, the player tab). It must match the
    service's own reading: the heatmap paints whatever ``effective_segments``
    returns, so a mismatch shows people the opposite of what the scheduler sees.

    ``help_snippet`` names the in-app help region to hang off the title. The two
    callers pass different ones on purpose: the editors look identical but hold
    different data and feed different things, which is the single most confusing
    thing about this surface.

    ``title_class`` exists because the two callers sit at different depths: the
    Volunteer hub gives this editor a whole tab, while Home stacks it as one
    section among several under My Schedule, where a second page-sized heading
    would compete with the tab's own.
    """
    user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if user is None:
        ui.label('You must be logged in.').classes('text-error')
        return

    event_start, event_end = await SystemConfigService.get_event_window()
    existing = await service.availability_for(user)
    open_ranges = await _open_ranges() if mode.shade_closed_hours else None

    # Calendar days spanned by the event window, on the display clock, as
    # (date, day_start_utc, day_end_utc) tuples for the graph.
    event_days: list[tuple] = []
    cursor = event_start
    last_day = event_end
    while cursor <= last_day:
        next_day = cursor + timedelta(days=1)
        event_days.append((
            cursor,
            parse_local_datetime(cursor.isoformat(), '00:00'),
            parse_local_datetime(next_day.isoformat(), '00:00'),
        ))
        cursor = next_day

    # Working set of rows; each is a mutable dict the inputs bind to. A stored
    # status this mode does not offer cannot be shown against a dropdown that
    # cannot represent it, so it is left out of the editor. Nothing writes one
    # today — PlayerAvailabilityService drops an AVAILABLE window on save — so
    # this catches rows that predate that rule, not a live case.
    rows: list[dict] = [
        row for row in (
            {
                'date': format_local_date(w.starts_at),
                'start': format_local_time(w.starts_at),
                'end': format_local_time(to_local(w.ends_at)),
                'status': w.status.value if hasattr(w.status, 'value') else str(w.status),
            }
            for w in existing
        )
        if row['status'] in mode.status_options
    ]

    with ui.column().classes('page-container'):
        # ``title=''`` means the caller has already given this editor a heading —
        # My Schedule wraps it in a section panel — so a second one here would
        # only repeat the words and re-add the header/separator margin the panel
        # exists to remove.
        if title:
            with ui.row().classes('header-row items-center'):
                ui.label(title).classes(title_class)
                if help_snippet:
                    await help_icon(help_snippet)
            ui.separator().classes('separator-spacing')
        ui.label(
            f'Event window: {format_local_date(event_start)} → {format_local_date(event_end)} '
            f'({timezone_label()}). {help_text}'
        ).classes('italic-note')

        @ui.refreshable
        def window_rows() -> None:
            if not rows:
                ui.label(mode.empty_text).classes('italic-note')
            for row in rows:
                with ui.row().classes('items-center gap-2 q-mb-xs'):
                    native_date_input('Date', row['date'], dense=True) \
                        .bind_value(row, 'date') \
                        .on_value_change(effective_graph.refresh)
                    native_time_input('Start', row['start'], dense=True) \
                        .bind_value(row, 'start') \
                        .on_value_change(effective_graph.refresh)
                    native_time_input('End', row['end'], dense=True) \
                        .bind_value(row, 'end') \
                        .on_value_change(effective_graph.refresh)
                    ui.select(mode.status_options, value=row['status']) \
                        .props('dense').bind_value(row, 'status').classes('w-40') \
                        .on_value_change(effective_graph.refresh)
                    ui.button(icon='delete', on_click=lambda r=row: _remove(r)) \
                        .props('flat dense color=negative')

        def _windows_from_rows() -> list:
            """Parse the working rows into window-like objects, skipping any
            that are incomplete or invalid (so the graph stays live as you edit)."""
            parsed = []
            for row in rows:
                if not row['date'] or not row['start'] or not row['end']:
                    continue
                try:
                    starts_at = parse_local_datetime(row['date'], row['start'])
                    ends_at = parse_local_datetime(row['date'], row['end'])
                    status = VolunteerAvailabilityStatus(row['status'])
                except (ValueError, KeyError):
                    continue
                if ends_at <= starts_at:
                    continue
                parsed.append(SimpleNamespace(starts_at=starts_at, ends_at=ends_at, status=status))
            return parsed

        @ui.refreshable
        def effective_graph() -> None:
            windows = _windows_from_rows()
            with ui.column().classes('w-full gap-1 q-mt-md'):
                ui.label('Effective availability').classes('text-subtitle2')
                ui.label(mode.precedence_text).classes('italic-note')
                with ui.row().classes('items-center gap-4 q-mb-xs'):
                    for legend_status in mode.legend_statuses:
                        with ui.row().classes('items-center gap-1 no-wrap'):
                            ui.element('div').classes(f'avail-swatch {_seg_class(legend_status)}')
                            ui.label(mode.label(legend_status)).classes('text-caption')
                    if open_ranges is not None:
                        with ui.row().classes('items-center gap-1 no-wrap'):
                            ui.element('div').classes(f'avail-swatch {_NONE_SEG_CLASS}')
                            ui.label(mode.closed_label).classes('text-caption')
                for day, day_start, day_end in event_days:
                    segments = service.effective_segments(windows, day_start, day_end)
                    total = (day_end - day_start).total_seconds()
                    with ui.row().classes('items-center no-wrap gap-2 w-full'):
                        ui.label(day.strftime('%a %b %d')).classes('text-caption avail-day-label')
                        with ui.element('div').classes('flex-grow avail-bar'):
                            if not segments:
                                ui.element('div').classes(_NONE_SEG_CLASS).style('width:100%')
                            for seg_start, seg_end, status in segments:
                                for part_start, part_end, is_open in _split_by_open(
                                    seg_start, seg_end, open_ranges,
                                ):
                                    pct = (part_end - part_start).total_seconds() / total * 100
                                    label = mode.label(status) if is_open else mode.closed_label
                                    css = _seg_class(status) if is_open else _NONE_SEG_CLASS
                                    seg = ui.element('div').classes(css).style(f'width:{pct}%')
                                    seg.tooltip(
                                        f'{format_local_time(part_start)}–'
                                        f'{format_local_time(part_end)} · {label}'
                                    )
                with ui.row().classes('items-center no-wrap gap-2 w-full'):
                    ui.label('').classes('avail-day-label')
                    with ui.row().classes('flex-grow justify-between no-wrap'):
                        for tick in ('00:00', '06:00', '12:00', '18:00', '24:00'):
                            ui.label(tick).classes('text-caption text-grey').style('white-space:nowrap')

        def _remove(row: dict) -> None:
            rows.remove(row)
            window_rows.refresh()
            effective_graph.refresh()

        def _add() -> None:
            start_hhmm, end_hhmm = mode.new_row_times
            rows.append({
                'date': format_local_date(event_start),
                'start': start_hhmm,
                'end': end_hhmm,
                'status': mode.new_row_status.value,
            })
            window_rows.refresh()
            effective_graph.refresh()

        window_rows()
        effective_graph()

        async def save() -> None:
            windows = []
            try:
                for row in rows:
                    if not row['date'] or not row['start'] or not row['end']:
                        raise ValueError('Every window needs a date, start, and end.')
                    starts_at = parse_local_datetime(row['date'], row['start'])
                    ends_at = parse_local_datetime(row['date'], row['end'])
                    if ends_at <= starts_at:
                        raise ValueError('Each availability window must end after it starts.')
                    status = VolunteerAvailabilityStatus(row['status'])
                    windows.append((starts_at, ends_at, status, None))
                await service.set_windows(user, windows)
            except (ValueError, PermissionError) as e:
                ui.notify(str(e), color='warning')
                return
            ui.notify('Availability saved.', color='positive')

        with ui.row().classes('q-mt-md gap-2'):
            ui.button(mode.add_button_text, icon='add', on_click=_add).props('flat color=primary')
            ui.button(mode.save_button_text, icon='save', on_click=save).props('color=primary')
