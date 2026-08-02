from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Optional

from nicegui import ui

from application.utils.timezone import (
    format_local_date,
    format_local_time,
    parse_local_datetime,
    timezone_label,
    to_local,
)


def datetime_to_local_input(value: Optional[datetime]) -> str:
    """A stored UTC instant → the ``datetime-local`` string that prefills it.

    Paired with :func:`local_input_to_datetime` so a value survives a round trip
    through the form on the display clock rather than drifting by the offset.
    """
    if value is None:
        return ''
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = to_local(value)
    return local.strftime('%Y-%m-%dT%H:%M') if local else ''


def local_input_to_datetime(value: Optional[str]) -> Optional[datetime]:
    """A ``datetime-local`` form value on the display clock → stored UTC, or None.

    Raises ``ValueError`` on a wall clock the zone skips, the same way
    :func:`application.utils.timezone.parse_local_datetime` does — callers show
    it rather than storing a time an hour from the one that was typed.
    """
    if not value or 'T' not in value:
        return None
    date_str, time_str = value.split('T', 1)
    return parse_local_datetime(date_str, time_str[:5])


@contextmanager
def form_dialog(title: str, *, card_classes: str = 'dialog-card'):
    """Standard inline add/edit dialog scaffold as a context manager.

    Opens ``ui.dialog()`` + ``ui.card()``, applies the mobile-sheet behaviour and
    the standard :func:`dialog_header`, then yields the ``dialog`` so the caller
    adds a body column, a :func:`dialog_actions` bar, and :func:`submit_on_enter`.
    Lets the inline admin-tab dialogs share the class-dialog chrome (mobile sheet,
    header, Enter-to-submit) instead of hand-rolling ``ui.dialog``/``ui.card``.

    Usage::

        with form_dialog('Add Webhook') as dialog:
            with ui.column().classes('q-pa-md gap-2 full-width'):
                name = ui.input('Name')
            with dialog_actions().classes('justify-end'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=submit).props('color=primary')
            submit_on_enter(dialog, submit)
        dialog.open()
    """
    with ui.dialog() as dialog, ui.card().classes(card_classes):
        mobile_sheet(dialog)
        dialog_header(title, dialog)
        yield dialog


def dialog_header(title: str, dialog) -> None:
    """Standard dialog header row: title + spacer + close button, then a separator.

    Call inside the dialog's ``ui.card()`` context so it nests correctly.
    """
    with ui.row().classes('dialog-header items-center q-pa-sm'):
        ui.label(title).classes('text-h6 q-ma-none')
        ui.space()
        ui.button(icon='close', on_click=dialog.close).props('flat round dense').tooltip('Close')
    ui.separator()


def dialog_actions():
    """Sticky bottom action bar for a dialog card, used as a context manager.

    Wrap the dialog's action buttons in ``with dialog_actions():``; the
    ``.dialog-actions`` class pins the row to the bottom of the scrolling card so
    the primary action stays visible without scrolling on mobile sheets.
    """
    return ui.row().classes('dialog-actions items-center gap-2')


def _native_props(
    input_type: str, *, required: bool, clearable: bool, dense: bool, stack_label: bool
) -> str:
    """Build the props string for a native date/time input."""
    props = f'type={input_type}'
    if stack_label:
        props += ' stack-label'
    if required:
        props += ' required'
    if clearable:
        props += ' clearable'
    if dense:
        props += ' dense'
    return props


def native_date_input(
    label: str,
    value: str = '',
    *,
    required: bool = False,
    clearable: bool = False,
    dense: bool = False,
    stack_label: bool = True,
):
    """A native ``type=date`` input (YYYY-MM-DD), so mobile gets the OS date picker.

    Returns the ``ui.input``; read/write its ``.value`` as a ``YYYY-MM-DD`` string.
    Centralizes the props string so the native-picker recipe lives in one place.
    """
    return ui.input(label, value=value).props(_native_props(
        'date', required=required, clearable=clearable, dense=dense, stack_label=stack_label,
    ))


def native_time_input(
    label: str,
    value: str = '',
    *,
    required: bool = False,
    dense: bool = False,
    stack_label: bool = True,
    tz=None,
    show_timezone: bool = True,
):
    """A native ``type=time`` input (HH:MM), so mobile gets the OS time picker.

    The label carries the zone the time will be read in — ``Time (EDT)``. A bare
    "Time" field was unambiguous only while the whole app ran on one clock; now
    that two people in different zones can fill in the same form, the field has
    to say which clock it means, or the value it stores is a guess.

    ``tz=None`` labels it with the viewer's own zone, which is what the paired
    ``parse_local_datetime`` will use. Pass an explicit ``tz`` where the field is
    **not** read on the viewer's clock — a tenant-anchored rule like tournament
    operating hours — so the label matches the zone that actually applies.
    ``show_timezone=False`` opts out for a field whose surrounding copy already
    says it, or one that is a duration rather than a wall clock.

    ``dense``/``stack_label`` exist because their absence is what drove callers to
    hand-roll the props string in the first place — and a hand-rolled field is one
    the zone label can never reach.
    """
    if show_timezone:
        label = f'{label} ({timezone_label(tz)})'
    return ui.input(label, value=value).props(_native_props(
        'time', required=required, clearable=False, dense=dense, stack_label=stack_label,
    ))


def native_datetime_input(
    label: str,
    value: str = '',
    *,
    required: bool = False,
    dense: bool = False,
    stack_label: bool = True,
    tz=None,
    show_timezone: bool = True,
):
    """A native ``type=datetime-local`` input (``YYYY-MM-DDTHH:MM``).

    One control for a date and a time together, where a separate pair would be
    noise. Carries the zone in its label for the same reason
    :func:`native_time_input` does — it names a wall clock, so it has to name the
    clock.
    """
    if show_timezone:
        label = f'{label} ({timezone_label(tz)})'
    return ui.input(label, value=value).props(_native_props(
        'datetime-local', required=required, clearable=False, dense=dense, stack_label=stack_label,
    ))


def render_suggest_time_button(
    dialog,
    *,
    get_tournament_id: Callable[[], object],
    get_player_ids: Callable[[], list],
    date,
    time,
    missing_message: str,
    get_bracket_match_id: Callable[[], object] = lambda: None,
) -> None:
    """The 'Suggest a time' button shared by every match-scheduling dialog.

    Fills ``date``/``time`` from :class:`MatchSuggestionService` on click, rather
    than silently pre-filling them on open — the suggestion should be a visible,
    reviewable action the scheduler asked for, not a value baked into the form
    before anyone looked at it. ``get_tournament_id``/``get_player_ids`` are
    evaluated at click time so callers can source them from selects that change
    after the dialog opens. ``get_bracket_match_id`` clamps the suggestion to a
    bracket matchup's round window; omit it outside a bracket-run tournament.
    """
    from application.services import MatchSuggestionService

    async def suggest_time():
        tournament_id = get_tournament_id()
        player_ids = get_player_ids()
        if not tournament_id or not player_ids:
            with dialog:
                ui.notify(missing_message, color='warning')
            return
        try:
            suggested = await MatchSuggestionService().suggest_match_time(
                tournament_id=tournament_id,
                player_ids=player_ids,
                bracket_match_id=get_bracket_match_id(),
            )
            date.value = format_local_date(suggested)
            time.value = format_local_time(suggested)
            with dialog:
                ui.notify('Suggested time filled in — review and save.', color='info')
        except ValueError as e:
            with dialog:
                ui.notify(str(e), color='warning')

    ui.button('Suggest a time', icon='lightbulb', on_click=suggest_time).props('flat color=secondary').classes('mt-1')


def mobile_sheet(dialog) -> None:
    """Make a dialog fill the screen as a maximized sheet on phones (<600px).

    NiceGUI evaluates dynamic props against the global ``Quasar`` object, not
    Vue ``$q``, so the breakpoint must reference ``Quasar.Screen.lt.sm``.
    """
    dialog.props(':maximized="Quasar.Screen.lt.sm"')


def submit_on_enter(dialog, make_coro) -> None:
    """Run an async submit handler when Enter is pressed inside the dialog.

    ``make_coro`` is a zero-arg callable returning the coroutine to run.
    """
    def on_keydown(e):
        if e.args and e.args.get('key') == 'Enter':
            # Return the coroutine so NiceGUI awaits it in the dialog's slot
            # context; a bare background task has no slot and any ui.notify /
            # ui.run_javascript in the submit handler would raise.
            return make_coro()
    dialog.on('keydown', on_keydown)
