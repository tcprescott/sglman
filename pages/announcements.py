
import asyncio
from nicegui import ui, app
from models import Announcement, Tournament
from tortoise.expressions import Q

async def announcements_page():
    async def enrolled_only_change(e):
        user['announcements_show_enrolled_only'] = show_enrolled_only.value
        await load_announcements()

    user = app.storage.user
    with ui.row().style('width: 100%; margin-bottom: 1em;'):
        ui.label('Announcements').style('font-size: 2em;')
    with ui.row().style('width: 100%;'):
        show_enrolled_only_value = user.get('announcements_show_enrolled_only', False)
        show_enrolled_only = ui.checkbox('Show only tournaments I am enrolled in', value=show_enrolled_only_value, on_change=enrolled_only_change) if user.get('discord_id') else None
    announcements_container = ui.row().style('width: 100%; flex-wrap: wrap; gap: 1em; margin-top: 1em; justify-content: flex-start;')


    async def get_enrolled_tournament_ids(discord_id):
        # Get tournaments the user is enrolled in
        enrolled = await Tournament.filter(players__user__discord_id=discord_id).values_list('id', flat=True)
        return set(enrolled)

    async def load_announcements():
        announcements_container.clear()
        discord_id = user.get('discord_id') if user else None
        show_only = show_enrolled_only.value
        if show_only and discord_id:
            enrolled_ids = await get_enrolled_tournament_ids(discord_id)
            query = Q(is_active=True) & (Q(tournament_id__in=enrolled_ids) | Q(tournament_id=None))
        else:
            query = Q(is_active=True)
        announcements = await Announcement.filter(query).order_by('-created_at').all()
        if not announcements:
            ui.label('No announcements found.').classes('text-caption')
            return
        # Show the most recent announcement in its own full-width row
        with announcements_container:
            most_recent = announcements[0]
            with ui.row().style('width: 100%; margin-bottom: 1em;'):
                card = ui.card().classes('q-pa-md').style('width: 100%; max-width: 100%; margin: 8px; display: flex; flex-direction: column;')
                with card:
                    ui.label(most_recent.title).classes('text-h5')
                    ui.html(most_recent.content).classes('q-mt-sm')
                    if most_recent.tournament_id:
                        tournament = await Tournament.get_or_none(id=most_recent.tournament_id)
                        if tournament:
                            ui.label(f'Tournament: {tournament.name}').classes('text-caption')
                    ui.label(f'Posted: {most_recent.created_at.strftime('%Y-%m-%d %H:%M')}').classes('text-caption')
            # Show the rest in the grid
            for ann in announcements[1:]:
                card = ui.card().classes('q-pa-md').style('width: 350px; min-width: 350px; max-width: 350px; margin: 8px; display: flex; flex-direction: column;')
                with card:
                    ui.label(ann.title).classes('text-h6')
                    ui.html(ann.content).classes('q-mt-sm')
                    if ann.tournament_id:
                        tournament = await Tournament.get_or_none(id=ann.tournament_id)
                        if tournament:
                            ui.label(f'Tournament: {tournament.name}').classes('text-caption')
                    ui.label(f'Posted: {ann.created_at.strftime('%Y-%m-%d %H:%M')}').classes('text-caption')
    await load_announcements()
