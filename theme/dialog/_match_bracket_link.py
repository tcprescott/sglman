"""The admin match editor's 'Bracket matchup' picker.

Split out of ``match_dialog`` to keep it under the file-length guideline. Plain
functions taking the :class:`BracketService` explicitly rather than a mixin —
only :class:`AdminMatchDialog` uses them, and the seam is one select plus one
reconcile step.

This is the counterpart of booking a game from the bracket view: staff who
scheduled a match through the ordinary editor can attach it to the matchup it
actually settles, so its result advances the bracket.
"""

from typing import Optional

from nicegui import app, background_tasks, ui

from application.services import get_user_from_discord_id


def matchup_label(bracket_match) -> str:
    """'Round 2 — Alice vs Bob', the way the bracket view names a matchup."""
    def name_of(entry):
        return entry.entrant.display_name if entry and entry.entrant else 'TBD'

    rnd = bracket_match.round
    base = f'Losers round {abs(rnd)}' if rnd < 0 else f'Round {rnd}'
    return (
        f'{base} — {name_of(bracket_match.entry1)} vs '
        f'{name_of(bracket_match.entry2)}'
    )


async def render_select(
    bracket_service,
    selected_tournament,
    *,
    brackets_live: bool,
    linked_id: Optional[int],
    match_id: Optional[int],
):
    """Optional 'Bracket matchup' picker, repopulated with the tournament.

    Returns the select, or ``None`` when brackets are off for this tenant — the
    caller then skips the link step entirely rather than reading a widget that
    isn't there.

    The currently-linked matchup is added to the options by hand: it is OPEN but
    its slot is already taken, so ``list_linkable_matches`` excludes it and the
    select would otherwise render blank on an already-linked match.
    """
    if not brackets_live:
        return None

    select = ui.select(
        label='Bracket matchup (optional)',
        options={None: '(None)'},
        value=linked_id,
        with_input=True,
    ).classes('input-full-width')
    select.tooltip(
        'Link this match to a bracket matchup so its result advances the bracket.'
    )

    async def repopulate():
        tournament_id = selected_tournament.value
        options = {None: '(None)'}
        if tournament_id:
            for bm in await bracket_service.list_linkable_matches(tournament_id):
                options[bm.id] = matchup_label(bm)
        if linked_id is not None and linked_id not in options and match_id is not None:
            linked = await bracket_service.get_bracket_match_for_match(match_id)
            if linked is not None:
                options[linked_id] = f'{matchup_label(linked)} (linked)'
        select.disable()
        select.options = options
        select.enable()

    await repopulate()
    selected_tournament.on(
        'update:model-value', lambda: background_tasks.create(repopulate()),
    )
    return select


async def apply_link(
    bracket_service, select, match_id: int, previous_id: Optional[int],
) -> None:
    """Reconcile the picker against the match's existing link, if it changed.

    Called after the match write, so the ``Match`` exists to link. Unlink first
    then link, so moving a match between matchups frees its old slot before
    claiming the new one.
    """
    if select is None:
        return
    chosen = select.value or None
    if chosen == previous_id:
        return

    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if previous_id is not None:
        await bracket_service.unlink_match(actor, match_id)
    if chosen is not None:
        await bracket_service.link_match_to_bracket_match(actor, chosen, match_id)
