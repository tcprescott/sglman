"""Admin Volunteer Roster page — view availability and manage qualifications."""

from datetime import datetime, timedelta, timezone

from nicegui import app, ui

from application.repositories.volunteer_qualification_repository import VolunteerQualificationRepository
from application.repositories.volunteer_profile_repository import VolunteerProfileRepository
from application.services import AuthService, get_user_from_discord_id
from application.services.volunteer_availability_service import VolunteerAvailabilityService
from application.services.volunteer_position_service import VolunteerPositionService
from application.services.volunteer_profile_service import VolunteerProfileService
from application.utils.timezone import format_eastern_date, format_eastern_time
from models import VolunteerAvailabilityStatus
from theme.dialog.volunteer_profile_dialog import VolunteerProfileDialog

_STATUS_ABBR = {
    VolunteerAvailabilityStatus.PREFERRED: 'Preferred',
    VolunteerAvailabilityStatus.AVAILABLE: 'Available',
    VolunteerAvailabilityStatus.UNAVAILABLE: 'Unavailable',
}

_COLUMNS = [
    {'name': 'name', 'label': 'Name', 'field': 'name', 'sortable': True, 'align': 'left'},
    {'name': 'opted_in', 'label': 'Opted In', 'field': 'opted_in', 'sortable': True, 'align': 'center'},
    {'name': 'qualifications', 'label': 'Qualifications', 'field': 'qualifications', 'align': 'left'},
    {'name': 'availability', 'label': 'Availability', 'field': 'availability', 'align': 'left'},
    {'name': 'actions', 'label': '', 'field': 'id', 'align': 'right'},
]


async def admin_volunteer_roster_page() -> None:
    actor = await get_user_from_discord_id(app.storage.user.get('discord_id'))
    if not await AuthService.can_manage_volunteers(actor):
        ui.label('You do not have permission to manage volunteers.').classes('text-error')
        return

    profile_service = VolunteerProfileService()
    position_service = VolunteerPositionService()
    availability_service = VolunteerAvailabilityService()
    qual_repo = VolunteerQualificationRepository()
    profile_repo = VolunteerProfileRepository()

    volunteers_by_id: dict = {}

    with ui.column().classes('page-container-wide'):
        with ui.row().classes('header-row items-center'):
            ui.label('Volunteer Roster').classes('page-title')
            ui.space()
            ui.button(icon='refresh', on_click=lambda: load_roster()) \
                .props('flat color=primary').tooltip('Refresh')
        ui.separator().classes('separator-spacing')

        table = ui.table(
            columns=_COLUMNS,
            rows=[],
            row_key='id',
        ).classes('full-width').props(':grid="Quasar.Screen.lt.md"')

        # --- Desktop cell slots ---

        table.add_slot('body-cell-opted_in', '''
            <q-td :props="props">
                <q-icon :name="props.value ? 'check_circle' : 'cancel'"
                        :color="props.value ? 'positive' : 'negative'" size="sm" />
            </q-td>
        ''')

        table.add_slot('body-cell-qualifications', '''
            <q-td :props="props">
                <template v-if="props.value">
                    <q-chip v-for="q in props.value.split(',')" :key="q"
                            dense outline color="primary" class="q-ma-xs">{{ q.trim() }}</q-chip>
                </template>
                <span v-else class="text-grey-7">—</span>
            </q-td>
        ''')

        table.add_slot('body-cell-availability', '''
            <q-td :props="props">
                <div v-if="props.value">
                    <div v-for="line in props.value.split('\\n')" :key="line"
                         class="text-caption">{{ line }}</div>
                </div>
                <span v-else class="text-grey-7">—</span>
            </q-td>
        ''')

        table.add_slot('body-cell-actions', '''
            <q-td :props="props">
                <q-btn flat dense icon="manage_accounts" color="primary"
                       @click="$parent.$emit('manage_volunteer', props.row)"
                       title="View availability &amp; qualifications" />
            </q-td>
        ''')

        # --- Mobile card slot ---

        table.add_slot('item', '''
            <div class="q-pa-xs col-xs-12 col-sm-6 col-md-4">
                <q-card bordered flat class="q-pa-sm">
                    <div class="row items-center q-mb-xs">
                        <div class="col-5 text-grey-7 text-caption">Name</div>
                        <div class="col-7 text-weight-medium">{{ props.row.name }}</div>
                    </div>
                    <div class="row items-center q-mb-xs">
                        <div class="col-5 text-grey-7 text-caption">Opted In</div>
                        <div class="col-7">
                            <q-icon :name="props.row.opted_in ? 'check_circle' : 'cancel'"
                                    :color="props.row.opted_in ? 'positive' : 'negative'" size="sm" />
                        </div>
                    </div>
                    <div class="row items-start q-mb-xs">
                        <div class="col-5 text-grey-7 text-caption">Qualifications</div>
                        <div class="col-7">
                            <template v-if="props.row.qualifications">
                                <q-chip v-for="q in props.row.qualifications.split(',')" :key="q"
                                        dense outline color="primary" class="q-ma-none">{{ q.trim() }}</q-chip>
                            </template>
                            <span v-else class="text-grey-7 text-caption">None</span>
                        </div>
                    </div>
                    <div class="row items-start q-mb-xs">
                        <div class="col-5 text-grey-7 text-caption">Availability</div>
                        <div class="col-7">
                            <template v-if="props.row.availability">
                                <div v-for="line in props.row.availability.split('\\n')" :key="line"
                                     class="text-caption">{{ line }}</div>
                            </template>
                            <span v-else class="text-grey-7 text-caption">None declared</span>
                        </div>
                    </div>
                    <div class="row justify-end q-mt-xs">
                        <q-btn flat dense icon="manage_accounts" color="primary"
                               @click="$parent.$emit('manage_volunteer', props.row)"
                               title="View availability &amp; qualifications" />
                    </div>
                </q-card>
            </div>
        ''')

        # --- Data loading ---

        async def load_roster() -> None:
            nonlocal volunteers_by_id

            now = datetime.now(timezone.utc)
            win_start = now - timedelta(days=365)
            win_end = now + timedelta(days=365)

            volunteers = await profile_service.assignable_volunteers()
            volunteers_by_id = {u.id: u for u in volunteers}

            positions = await position_service.list_all()
            position_by_id = {p.id: p for p in positions}

            opted_in_ids = set(await profile_repo.opted_in_user_ids())

            all_quals = await qual_repo.list_all()
            qual_map: dict[int, list[str]] = {}
            for q in all_quals:
                pos = position_by_id.get(q.position_id)
                if pos:
                    qual_map.setdefault(q.user_id, []).append(pos.name)

            avail_map = await availability_service.availability_map(
                [u.id for u in volunteers], win_start, win_end,
            )

            rows = []
            for volunteer in volunteers:
                windows = sorted(avail_map.get(volunteer.id, []), key=lambda w: w.starts_at)
                avail_lines = [
                    f'{_STATUS_ABBR.get(w.status, w.status)}: '
                    f'{format_eastern_date(w.starts_at)} '
                    f'{format_eastern_time(w.starts_at)}–{format_eastern_time(w.ends_at)} ET'
                    for w in windows
                ]
                rows.append({
                    'id': volunteer.id,
                    'name': volunteer.preferred_name,
                    'opted_in': volunteer.id in opted_in_ids,
                    'qualifications': ', '.join(sorted(qual_map.get(volunteer.id, []))),
                    'availability': '\n'.join(avail_lines),
                })

            table.rows = rows
            table.update()

        # --- Event handler ---

        async def handle_manage(event) -> None:
            row = event.args if isinstance(event.args, dict) else {}
            user_id = row.get('id')
            user = volunteers_by_id.get(user_id)
            if not user:
                ui.notify('Volunteer not found.', color='warning')
                return
            active_positions = await position_service.list_active()
            await VolunteerProfileDialog(
                user=user,
                positions=active_positions,
                on_submit=load_roster,
            ).open()

        table.on('manage_volunteer', handle_manage)

        await load_roster()
