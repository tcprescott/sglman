"""Shared behaviour for the admin and player match dialogs.

Split out of ``match_dialog.py`` when that module reached the 800-line
guideline; the two concrete dialogs still live there.
"""

from typing import Awaitable, Callable

from nicegui import app, background_tasks, context, ui

from application.services import (
    BracketService,
    CrewService,
    MatchService,
    MatchStreamVolunteerService,
    MatchWatcherService,
    StageService,
    TournamentService,
    UserService,
    get_user_from_discord_id,
)
from application.utils.timezone import (
    format_local_date,
    format_local_time,
    now_local,
)
from models import Match
from theme.dialog._helpers import (
    dialog_actions,
    dialog_header,
    native_date_input,
    native_time_input,
    render_suggest_time_button,
    submit_on_enter,
)
from theme.dialog.confirmation_dialog import ConfirmationDialog
from theme.notify import notify_error


def enrolment_preview(names: list, tournament_name: str) -> str:
    """The sentence naming who scheduling this match will enrol.

    Empty when everyone chosen is already an entrant, so it says nothing on the
    common path — the point is to surface a side effect, not to add noise.
    """
    if not names:
        return ''
    if len(names) == 1:
        return f'{names[0]} will be enrolled in {tournament_name}.'
    listed = ', '.join(names[:-1]) + f' and {names[-1]}'
    return f'{listed} will be enrolled in {tournament_name}.'


#: Semantic tone (``match_status.STATUS_TONES``) → the chip class ``styles.css``
#: already defines. One mapping so the dialog's chip and the board's cell cannot
#: colour the same state differently.
_TONE_CHIP = {
    'neutral': 'wiz-chip--neutral',
    'info': 'wiz-chip--neutral',
    'imminent': 'wiz-chip--candidate',
    'live': 'wiz-chip--live',
    'done': 'wiz-chip--pending',
    'settled': 'wiz-chip--ok',
    'cancelled': 'wiz-chip--cancelled',
    'attention': 'wiz-chip--pending',
}


def acknowledgment_empty_state(player_count: int, sg_sourced: bool) -> str:
    """What to say when a match has no acknowledgment rows.

    The old copy said "No players assigned." for a match with two players and
    zero rows — describing the wrong thing entirely, and on the exact matches a
    SpeedGaming sync produced. Distinguish the two states, and on a sourced
    match name the cause rather than leaving the operator to guess.
    """
    if player_count == 0:
        return 'No players assigned yet.'
    plural = 'player is' if player_count == 1 else 'players are'
    base = (f'{player_count} {plural} assigned, but nobody has been asked to '
            f'confirm — there are no acknowledgment rows on this match.')
    if sg_sourced:
        return base + ' Re-syncing this episode from SpeedGaming creates them.'
    return base


def enrolment_report(names: list, tournament_name: str) -> str:
    """The same fact in the past tense, for the success notification."""
    if not names:
        return ''
    if len(names) == 1:
        return f'{names[0]} was enrolled in {tournament_name}.'
    listed = ', '.join(names[:-1]) + f' and {names[-1]}'
    return f'{listed} were enrolled in {tournament_name}.'


class BaseMatchDialog:
    """Base class for match dialogs with common functionality."""

    def __init__(self, match: Match = None, on_submit=None):
        self.match = match
        self.on_submit = on_submit
        self.dialog = None
        self._clear_seated = False
        self._clear_started = False
        self._clear_finished = False
        self._clear_confirmed = False
        self._clear_seed = False
        self._initial_updated_at = match.updated_at if match else None
        self.match_service = MatchService()
        self.user_service = UserService()
        self.crew_service = CrewService()
        self.tournament_service = TournamentService()
        self.stage_service = StageService()
        self.bracket_service = BracketService()

    def _get_default_values(self):
        now = now_local()
        if self.match:
            return {
                'tournament': self.match.tournament_id if self.match.tournament_id else None,
                'date': format_local_date(self.match.scheduled_at) if self.match.scheduled_at else now.strftime('%Y-%m-%d'),
                'time': format_local_time(self.match.scheduled_at) if self.match.scheduled_at else now.strftime('%H:%M'),
                'comment': self.match.comment or '',
                'stage': self.match.stage_id if self.match.stage_id else None,
            }
        else:
            return {
                'tournament': None,
                'date': now.strftime('%Y-%m-%d'),
                'time': now.strftime('%H:%M'),
                'comment': '',
                'stage': None,
            }

    def _render_tournament_select(
        self, tournaments, default_value, empty_hint, entrant_counts=None,
    ):
        """The Tournament select, optionally labelled with each entrant count.

        ``entrant_counts`` turns *"why is the Players menu empty?"* into a fact
        readable before the choice is made — the admin dialog passes it, the
        player's request dialog has no use for it (its own list is already
        enrolment-scoped).
        """
        def option_label(t) -> str:
            if entrant_counts is None:
                return t.name
            n = entrant_counts.get(t.id, 0)
            if n == 0:
                return f'{t.name} — nobody enrolled'
            return f'{t.name} — {n} entrant{"" if n == 1 else "s"}'

        select = ui.select(
            label='Tournament *',
            options={t.id: option_label(t) for t in tournaments},
            value=default_value,
            with_input=True,
        ).props('required').classes('input-full-width')
        if not tournaments:
            # Otherwise a required select with no options opens no menu and
            # answers "Please fill required field(s): Tournament".
            select.disable()
            select.props(f'hint="{empty_hint}"')
        return select

    def _render_date_time_inputs(self, default_date, default_time):
        with ui.row().classes('items-center gap-2'):
            date = native_date_input('Date', default_date, required=True)
            time = native_time_input('Time', default_time, required=True)

        return date, time

    def _render_suggest_time_button(
        self,
        *,
        get_tournament_id: Callable[[], object],
        get_player_ids: Callable[[], list],
        date,
        time,
        missing_message: str,
    ) -> None:
        """Render the 'Suggest a time' button shared by every scheduling dialog.

        The two callers on this class source player ids differently (admin from
        the players multi-select, user from the single opponent select plus
        their own id), so the ids are supplied by ``get_player_ids``, evaluated
        at click time.
        """
        render_suggest_time_button(
            self.dialog,
            get_tournament_id=get_tournament_id,
            get_player_ids=get_player_ids,
            date=date,
            time=time,
            missing_message=missing_message,
        )

    def _render_state_summary(self, players) -> None:
        """Where this match currently stands, at the top of the edit dialog.

        The dialog used to read none of it: opening a Finished, disputed match
        with a winner already recorded showed a Comment field, five Clear
        buttons and the sentence "No players assigned." The three facts that
        explain why the match is in front of you — its state, the recorded
        winner, the proctor's dispute flag — all lived on the board behind it.
        """
        from application.services.match.match_status import (
            LEGACY_STATE_LABELS,
            STATUS_LABELS,
            STATUS_TONES,
            resolve,
        )

        status = resolve(match=self.match)
        text = LEGACY_STATE_LABELS.get(status) or STATUS_LABELS.get(status, '')
        chip = _TONE_CHIP.get(STATUS_TONES.get(status, 'neutral'), 'wiz-chip--neutral')
        winner = next((p for p in players if getattr(p, 'finish_rank', None) == 1), None)

        with ui.row().classes('items-center gap-2 flex-wrap'):
            with ui.element('span').classes(f'wiz-chip {chip}'):
                ui.label(text)
            if winner is not None:
                with ui.element('span').classes('wiz-chip wiz-chip--ok'):
                    ui.icon('emoji_events', size='14px')
                    ui.label(f'Winner: {winner.user.preferred_name}')
            if getattr(self.match, 'needs_review', False):
                with ui.element('span').classes('wiz-chip wiz-chip--cancelled'):
                    ui.icon('report_problem', size='14px')
                    ui.label('Needs review')
        if getattr(self.match, 'needs_review', False):
            ui.label(
                'Flagged by the proctor. Confirming the result clears the flag.'
            ).classes('text-caption st-pending')

    def _render_clear_buttons(self):
        """The five buttons that rewind a match's lifecycle on Save.

        They arm rather than act, which is right — the change belongs in the one
        transaction the Save runs. What was missing was every other half of an
        arming mechanism: nothing said the buttons rolled the lifecycle
        backwards, a click only greyed the button out, there was no way to
        change your mind short of closing the dialog and losing every other
        edit, and Save never summarised what it was about to undo. All three are
        here now; the buttons toggle, and ``_clear_summary`` is the sentence the
        Save confirmation reads back.
        """
        armed: dict = {}

        def make_clear_button(label, noun, icon, attr_flag, match_attr, is_relation=False):
            if is_relation:
                unavailable = getattr(self.match, f'{match_attr}_id', None) is None
            else:
                unavailable = getattr(self.match, match_attr) is None

            def toggle():
                now_armed = not getattr(self, attr_flag)
                setattr(self, attr_flag, now_armed)
                armed[noun] = now_armed
                if now_armed:
                    btn.props(remove='outline')
                    btn.props('color=negative')
                    btn.set_text(f'{label} — armed')
                else:
                    btn.props('outline color=negative')
                    btn.set_text(label)
                refresh_summary()

            btn = ui.button(label, icon=icon, on_click=toggle).props(
                f"outline color={'grey-7' if unavailable else 'negative'}",
            ).classes('ml-1')
            if unavailable:
                btn.disable()
                btn.tooltip(f'{noun} is not set on this match')
            return btn

        def refresh_summary() -> None:
            summary.text = self._clear_summary(armed)
            summary.set_visibility(bool(summary.text))

        with ui.column().classes('gap-1'):
            ui.label('Rewind the lifecycle').classes('text-bold')
            ui.label(
                'Each button arms a step to be undone when you press Save. '
                'Click it again to change your mind.'
            ).classes('text-caption text-grey')
            with ui.row().classes('items-center flex-wrap gap-1'):
                make_clear_button('Clear Check In', 'Check In', 'chair', '_clear_seated', 'seated_at')
                make_clear_button('Clear Started', 'Started', 'play_arrow', '_clear_started', 'started_at')
                make_clear_button('Clear Finish', 'Finish', 'sports_score', '_clear_finished', 'finished_at')
                make_clear_button('Clear Confirmed', 'Confirmed', 'verified', '_clear_confirmed', 'confirmed_at')
                make_clear_button('Clear Seed', 'Seed', 'casino', '_clear_seed', 'generated_seed', is_relation=True)
            summary = ui.label('').classes('text-caption st-pending')
            summary.set_visibility(False)

    @staticmethod
    def _clear_summary(armed: dict) -> str:
        """"Save will undo: X and Y." — empty when nothing is armed.

        Static and dict-driven so the sentence is testable without a browser;
        the five buttons above and the Save confirmation both read it, so they
        cannot describe the same arming differently.
        """
        names = [noun for noun, is_armed in armed.items() if is_armed]
        if not names:
            return ''
        listed = names[0] if len(names) == 1 else ', '.join(names[:-1]) + f' and {names[-1]}'
        return f'Save will undo: {listed}.'

    async def _render_watch_switch(self, user):
        if not self.match:
            return
        watcher_service = MatchWatcherService()
        initial_watching = await watcher_service.is_watching(self.match.id, user)
        match_id = self.match.id

        switch_ref = {}

        async def on_change(event, client):
            new_value = bool(event.value)
            try:
                if new_value:
                    await watcher_service.watch(match_id, user)
                    with client:
                        # The dialog *is* the match — naming it again (or worse,
                        # quoting its id) tells the reader nothing.
                        ui.notify(
                            'Now watching this match. You will receive Discord DMs on updates.',
                            color='positive',
                        )
                else:
                    await watcher_service.unwatch(match_id, user)
                    with client:
                        ui.notify('No longer watching this match.', color='positive')
            except ValueError as e:
                switch_ref['widget'].value = not new_value
                switch_ref['widget'].update()
                with client:
                    ui.notify(str(e), color='warning')

        switch_ref['widget'] = ui.switch(
            'Watch this match (Discord DM updates)',
            value=initial_watching,
            on_change=lambda e: background_tasks.create(on_change(e, context.client)),
        )

    async def _render_stream_volunteer_switch(self, user):
        """The players' "we'd be happy to be streamed" offer.

        The caption under the switch is not decoration: this control sits in a
        dialog full of things that *do* something, and without it the switch
        reads as claiming a stage. Staff decide; this only tells them.
        """
        if not self.match:
            return
        service = MatchStreamVolunteerService()
        try:
            initial = await service.has_volunteered(self.match.id, user)
        except ValueError:
            return
        match_id = self.match.id

        switch_ref: dict = {}

        async def on_change(event, client):
            new_value = bool(event.value)
            try:
                if new_value:
                    await service.volunteer(match_id, user)
                    with client:
                        ui.notify(
                            'Offered for stream. Staff see this when they plan '
                            'coverage — it does not guarantee the match goes out.',
                            color='positive',
                        )
                else:
                    await service.withdraw(match_id, user)
                    with client:
                        ui.notify('No longer offered for stream.', color='positive')
            except ValueError as e:
                switch_ref['widget'].value = not new_value
                switch_ref['widget'].update()
                with client:
                    ui.notify(str(e), color='warning')

        switch_ref['widget'] = ui.switch(
            'Offer this match for stream',
            value=initial,
            on_change=lambda e: background_tasks.create(on_change(e, context.client)),
        )
        ui.label(
            'Advisory only. Staff read it while they plan stream coverage; it '
            'does not book a stage or guarantee anything.'
        ).classes('text-caption text-grey-7')

    def _confirm_delete(self, dialog):
        async def on_confirm():
            await self._delete_match(dialog)
        ConfirmationDialog(
            message="Are you sure you want to delete this match?",
            on_confirm=on_confirm,
            confirm_text="Delete",
            cancel_text="Cancel",
        ).open()

    async def _delete_match(self, dialog):
        try:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await self.match_service.delete_match(self.match.id, actor=actor)
            with dialog:
                ui.notify('Match deleted', color='negative')
                dialog.close()
            if self.on_submit:
                await self.on_submit(None)
        except (ValueError, PermissionError) as e:
            with dialog:
                notify_error(e)

    def _confirm_cancel(self, dialog):
        async def on_confirm():
            await self._cancel_match(dialog)
        ConfirmationDialog(
            message=(
                "Cancel this match? Its players and crew will be DMed, and any "
                "open race room will be closed."
            ),
            on_confirm=on_confirm,
            confirm_text="Cancel match",
            cancel_text="Back",
        ).open()

    async def _cancel_match(self, dialog):
        try:
            actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
            await self.match_service.cancel_match(self.match.id, actor=actor)
            with dialog:
                ui.notify('Match cancelled — players and crew notified', color='negative')
                dialog.close()
            if self.on_submit:
                await self.on_submit(None)
        except (ValueError, PermissionError) as e:
            with dialog:
                notify_error(e)

    async def _tournament_name(self, tournament_id) -> str:
        tournament = await self.tournament_service.get_tournament_by_id(tournament_id)
        return tournament.name if tournament else 'this tournament'

    @staticmethod
    def stale_edit_message(base: str, latest) -> str:
        """The refusal, plus what the other admin actually changed.

        Naming the fields turns "someone got there first" into a decision the
        operator can make: overwriting a comment is not the same as overwriting
        a result somebody just confirmed.
        """
        changed = [
            label for label, value in (
                ('checked it in', getattr(latest, 'seated_at', None)),
                ('started it', getattr(latest, 'started_at', None)),
                ('finished it', getattr(latest, 'finished_at', None)),
                ('confirmed the result', getattr(latest, 'confirmed_at', None)),
                ('cancelled it', getattr(latest, 'cancelled_at', None)),
            ) if value is not None
        ]
        lines = [base]
        if changed:
            listed = (changed[0] if len(changed) == 1
                      else ', '.join(changed[:-1]) + f' and {changed[-1]}')
            lines.append(f'The match has since been {listed}.')
        return '\n\n'.join(lines)

    def _offer_stale_resolution(self, dialog, latest, stale_message: str, *, overwrite) -> None:
        """A way out of the optimistic lock, instead of a refusal on a loop.

        The lock is right; the recovery was missing. Saving over a match another
        admin had already saved answered "modified by another admin — reload and
        try again" with no reload, discard or overwrite anywhere in the dialog,
        and every subsequent Save repeated it forever. The only way forward was
        to select the typed text by hand, copy it out, close, reopen and retype.

        Two named exits: keep this edit (re-baseline against what is now stored
        and save over it) or drop it (close, their version stands).
        """
        async def take_mine() -> None:
            choice.close()
            # Re-baseline: the operator has now been told what they are
            # overwriting, so the guard has done its job and must not fire again.
            self._initial_updated_at = latest.updated_at
            await overwrite()

        def take_theirs() -> None:
            # Their version stands, so this dialog has nothing left to show —
            # every input in it is the losing copy.
            choice.close()
            dialog.close()

        # Built inline rather than through ConfirmationDialog: both exits act,
        # and its cancel button only closes itself.
        with ui.dialog() as choice, ui.card().classes('dialog-card'):
            dialog_header('Someone else saved this match first', choice)
            with ui.column().classes('q-pa-md'):
                ui.label(self.stale_edit_message(stale_message, latest)).style(
                    'white-space: pre-line')
            with dialog_actions().classes('justify-end'):
                ui.button('Discard mine', on_click=take_theirs).props('flat')
                ui.button(
                    'Save mine anyway',
                    on_click=lambda: background_tasks.create(take_mine()),
                ).props('color=negative')
        choice.open()

    async def _run_submit(
        self,
        dialog,
        *,
        required_fields: dict,
        tournament_id,
        player_ids: list,
        stale_message: str,
        do_update: Callable[[], Awaitable[None]],
        do_create: Callable[[], Awaitable[None]],
        create_success_message: str,
    ) -> None:
        """Shared submit pipeline for both match dialogs.

        Covers the mechanics both ``open()`` submit handlers share: required-field
        validation, ``ensure_players_enrolled``, the optimistic-lock ``updated_at``
        check on edit, and the ``PermissionError``/``ValueError`` handling ladder.
        The dialog-specific service calls are supplied by ``do_update``/``do_create``.

        ``required_fields`` is an ordered ``{label: value}`` mapping; any falsy value
        marks its label as missing.
        """
        missing = [label for label, value in required_fields.items() if not value]
        if missing:
            with self.dialog:
                ui.notify(f'Please fill required field(s): {", ".join(missing)}.', color='warning')
            return

        try:
            newly_enrolled = await self.match_service.ensure_players_enrolled(
                tournament_id, player_ids,
            )
        except ValueError as e:
            with self.dialog:
                notify_error(e)
            return

        if self.match:
            async def save() -> None:
                try:
                    await do_update()
                    with self.dialog:
                        ui.notify('Match updated successfully', color='positive')
                        dialog.close()
                    if self.on_submit:
                        await self.on_submit(self.match)
                except (ValueError, PermissionError) as e:
                    with self.dialog:
                        notify_error(e)

            latest_match = await self.match_service.get_match_by_id(self.match.id)
            if latest_match and latest_match.updated_at != self._initial_updated_at:
                with self.dialog:
                    self._offer_stale_resolution(
                        dialog, latest_match, stale_message, overwrite=save,
                    )
                return

            await save()
        else:
            try:
                await do_create()
                with self.dialog:
                    # Say what scheduling the match did besides schedule it.
                    report = enrolment_report(
                        [u.preferred_name for u in newly_enrolled],
                        await self._tournament_name(tournament_id),
                    )
                    ui.notify(
                        f'{create_success_message} — {report}' if report
                        else create_success_message,
                        color='positive',
                    )
                    dialog.close()
                if self.on_submit:
                    await self.on_submit()
            except (ValueError, PermissionError) as e:
                with self.dialog:
                    notify_error(e)

    def _render_submit_footer(self, dialog, submit, *, create_label: str) -> None:
        """Render the shared footer (Delete/Cancel/primary) and wire Enter-to-submit.

        ``create_label`` is the primary-button text used when creating a new match
        ('Create' for admin, 'Submit' for user); editing always shows 'Save'.
        """
        with dialog_actions():
            if self.match:
                ui.button('Delete', on_click=lambda: self._confirm_delete(dialog)).props('color=negative flat')
                # Distinct from the footer's 'Cancel' (which just closes this
                # dialog): calling the match off notifies everyone who committed
                # to it, where Delete is the silent "this shouldn't exist" path.
                ui.button('Cancel match', on_click=lambda: self._confirm_cancel(dialog)).props('color=negative flat')
            ui.space()
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save' if self.match else create_label, on_click=submit).props('color=primary')

        submit_on_enter(dialog, submit)
        dialog.open()

    async def open(self):
        raise NotImplementedError("Subclasses must implement open()")
