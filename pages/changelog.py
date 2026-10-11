"""The in-app changelog at ``/changelog``.

**Anonymous-readable**, like ``/help``: it describes the app, not a community's
data, so there is nothing on it a signed-out visitor should not see. Entries come
from ``application/changelog/`` (``changelog.md`` plus the per-PR ``changes/``
files) and render through the same safe block renderer as help, never NiceGUI's
markdown element. It has no menu
item of its own: the Help index links it, and it links back.
"""

from nicegui import app, ui

from application.changelog import ChangelogEntry, all_entries
from application.services import AuthService, TenantService, get_user_from_discord_id
from middleware.auth import public_page
from theme.base import BaseLayout
from theme.help.render import render_blocks
from theme.page_header import page_header

__all__ = ['create']


def _entry(entry: ChangelogEntry) -> None:
    with ui.element('div').classes('wiz-help-prose wiz-changelog-entry'):
        heading = ui.element('h2').classes('wiz-help-h2') \
            .props(f'id={entry.anchor}')
        with heading:
            ui.label(entry.title).classes('wiz-help-inline')
        ui.label(entry.period).classes('wiz-changelog-period text-caption text-grey-7')
        render_blocks(entry.blocks)


def create() -> None:
    @public_page('/changelog')
    async def changelog() -> None:
        community = await TenantService.current_community_name() or 'Wizzrobe'
        ui.page_title(f"What's new — {community}")
        user = await get_user_from_discord_id(app.storage.user.get('discord_id'))
        await BaseLayout(
            user=user, show_admin=await AuthService.can_view_admin(user),
        ).render()

        with ui.column().classes('page-container-narrow w-full'):
            ui.link('← All help', '/help').classes('text-caption')
            page_header("What's new")
            ui.label(
                'The bigger changes to Wizzrobe, about a week at a time, newest first.'
            ).classes('text-muted')

            entries = all_entries()
            if not entries:
                ui.label('Nothing to show yet.').classes('text-muted q-mt-md')
            for index, entry in enumerate(entries):
                if index:
                    ui.separator().classes('separator-spacing')
                _entry(entry)
