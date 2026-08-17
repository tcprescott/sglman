"""The pieces more than one ``/platform`` section needs.

``pages/platform.py`` is the page; each section it stacks lives in its own
module (``platform_bots``, ``platform_feature_groups``, ``platform_tenant_admins``)
because the page kept running at the file-length guideline. Anything two of them
share lands here rather than being imported from the page — that direction would
be a cycle.
"""

from nicegui import app

from application.services import get_user_from_discord_id

#: Active-column icon slot (check_circle / cancel), matching the styled admin
#: tables. Rows must carry an ``active_bool`` boolean.
ACTIVE_ICON_SLOT = '''
    <q-td :props="props">
        <q-icon :name="props.row.active_bool ? 'check_circle' : 'cancel'"
                :color="props.row.active_bool ? 'positive' : 'negative'" size="sm" />
    </q-td>
'''


async def current_actor():
    """The signed-in super-admin, re-read for a refresh outside a click handler."""
    return await get_user_from_discord_id(app.storage.user.get('discord_id'))
