"""Grid (mobile) slot builder for the match table.

Below Quasar's ``lt.md`` breakpoint ``ui.table`` renders the ``item`` slot per
row instead of columns. This module builds that single card template from the
column definitions, driven by the same server-injected admin/can_crud booleans
and per-field discord id the column slots use (``match_slots.py``).
"""


def render_grid_slot(table, columns, *, admin_controls: bool, can_crud: bool, discord_id) -> None:
    """Register the grid ``item`` slot on ``table`` from ``columns``."""
    # Dynamically generate grid slot fields from the columns
    grid_fields = []
    for col in columns:
        if col.get('hidden'):  # Skip hidden columns
            continue

        field = {
            'label': col.get('label', col.get('name', '')),
            'key': col.get('name', ''),
            'discord_id': f"'{discord_id}'" if discord_id else 'null'  # Format for JS template
        }

        # Special handling for different field types
        if field['key'] == 'id':
            field['event'] = 'edit_match'
        elif field['key'] == 'players':
            field['array'] = True
            field['separator'] = ', '  # Add space after comma
        elif field['key'] in ['commentators', 'trackers']:
            field['array_objects'] = True
            field['separator'] = ', '  # Add space after comma
        elif field['key'] == 'acknowledgments':
            field['ack_field'] = True
        elif field['key'] == 'state':
            field['state_field'] = True
        elif field['key'] == 'watch':
            field['watch_field'] = True

        grid_fields.append(field)

    # Build JS array for Vue template
    js_field_array = ',\n    '.join([
        f"{{ label: '{f['label']}', key: '{f['key']}'" +
        (f", event: '{f['event']}'" if 'event' in f else '') +
        (", array: true" if f.get('array') else '') +
        (", arrayObjects: true" if f.get('array_objects') else '') +
        (", ackField: true" if f.get('ack_field') else '') +
        (", stateField: true" if f.get('state_field') else '') +
        (", watchField: true" if f.get('watch_field') else '') +
        (f", separator: '{f['separator']}'" if 'separator' in f else '') +
        (f", discord_id: {f['discord_id']}" if 'discord_id' in f else '') +
        " }" for f in grid_fields
    ])

    table.add_slot('item', f'''
    <div class="q-pa-md q-mb-sm match-grid-card" :class="props.row._flash ? 'sgl-row-flash' : ''" style="width: 100%; box-sizing: border-box; border: 1px solid #eee; border-radius: 8px; background: #fff;">
        <div v-for="field in [
            {js_field_array}
        ]" :key="field.key" class="row items-center q-mb-xs">
            <div class="col-4 text-grey-7">{{{{ field.label }}}}:</div>
            <div class="col-8">
                <!-- For fields with click events like match ID -->
                <template v-if="field.event">
                    <a href="#" @click="$parent.$emit(field.event, {{ row: props.row }})" style="color: var(--sgl-link); text-decoration: underline;">{{{{ props.row[field.key] }}}}</a>
                </template>

                <!-- For array fields like players -->
                <template v-else-if="field.array">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div v-if="field.key === 'players'">
                            <template v-for="(player, idx) in props.row[field.key]">
                                <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                                    <q-icon v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged"
                                            name="check_circle" class="st-ok" size="xs">
                                        <q-tooltip v-if="props.row.acknowledgments[idx].ts">Acknowledged {{{{ props.row.acknowledgments[idx].ts }}}}</q-tooltip>
                                    </q-icon>
                                    <q-icon v-else-if="props.row.acknowledgments && props.row.acknowledgments[idx]"
                                            name="schedule" class="st-pending" size="xs">
                                        <q-tooltip>Awaiting acknowledgment</q-tooltip>
                                    </q-icon>
                                    <span :class="player.finish_rank === 1 ? 'st-ok-strong' : ''">
                                        {{{{ player.name }}}}
                                        <span v-if="{'true' if admin_controls else 'false'} && player.station" class="st-neutral italic-note"> ({{{{ player.station }}}})</span>
                                    </span>
                                    <span v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && props.row.acknowledgments[idx].acknowledged && props.row.acknowledgments[idx].auto"
                                          class="st-neutral italic-note" style="font-size: 0.85em;"> (auto)</span>
                                    <q-btn v-if="props.row.acknowledgments && props.row.acknowledgments[idx] && !props.row.acknowledgments[idx].acknowledged && props.row.acknowledgments[idx].discord_id && props.row.acknowledgments[idx].discord_id == field.discord_id"
                                           icon="check" color="primary" size="xs" dense flat
                                           @click="$parent.$emit('acknowledge_match', props.row)">
                                        <q-tooltip>Acknowledge</q-tooltip>
                                    </q-btn>
                                </div>
                            </template>
                        </div>
                        <span v-else>{{{{ Array.isArray(props.row[field.key]) ? props.row[field.key].join(field.separator || ', ') : props.row[field.key] }}}}</span>
                        <q-btn v-if="{'true' if (admin_controls and can_crud) else 'false'} && field.key === 'players'"
                               @click="$parent.$emit('assign_stations', {{ row: props.row }})"
                               icon="switch_access_shortcut" color="primary" size="xs" flat round>
                            <q-tooltip>Assign Stations</q-tooltip>
                        </q-btn>
                    </div>
                </template>

                <!-- For array of objects like commentators/trackers with approval status -->
                <template v-else-if="field.arrayObjects">
                    <span>
                        <!-- Add signup/undo buttons for commentator/tracker fields (non-admin only) -->
                        <template v-if="(field.key === 'commentators' || field.key === 'trackers') && !{'true' if admin_controls else 'false'}">
                            <div style="margin-bottom: 8px;">
                                <q-btn v-if="props.row[field.key] && props.row[field.key].some(item => item.discord_id == field.discord_id)"
                                       icon="undo" color="negative" size="sm"
                                       @click="$parent.$emit('undo_' + field.key.slice(0, -1), props.row)"
                                       style="margin-right: 8px;">
                                    Undo
                                </q-btn>
                                <q-btn v-if="props.row[field.key] && !props.row[field.key].some(item => item.discord_id == field.discord_id) && !props.row.players.some(p => p.discord_id == field.discord_id)"
                                       icon="assignment" color="primary" size="sm"
                                       @click="$parent.$emit('signup_' + field.key.slice(0, -1), props.row)"
                                       style="margin-right: 8px;">
                                    Sign Up
                                </q-btn>
                            </div>
                        </template>

                        <template v-if="Array.isArray(props.row[field.key])">
                            <template v-for="(item, idx) in props.row[field.key]">
                                <span style="display: inline-flex; align-items: center; gap: 2px;">
                                    <q-icon v-if="(field.key === 'commentators' || field.key === 'trackers') && item.approved && item.acknowledged"
                                            name="check_circle" class="st-ok" size="xs">
                                        <q-tooltip v-if="item.ack_ts">Acknowledged {{{{ item.ack_ts }}}}</q-tooltip>
                                    </q-icon>
                                    <q-icon v-else-if="(field.key === 'commentators' || field.key === 'trackers') && item.approved && !item.acknowledged"
                                            name="schedule" class="st-pending" size="xs">
                                        <q-tooltip>Approved, awaiting acknowledgment</q-tooltip>
                                    </q-icon>
                                    <template v-if="(field.key === 'commentators' || field.key === 'trackers') && {'true' if (admin_controls and can_crud) else 'false'}">
                                        <a href="#" @click="$parent.$emit('edit_' + field.key.slice(0, -1), {{ row: props.row, idx }})"
                                           :class="item.approved ? 'st-ok-strong' : 'st-pending'" style="text-decoration: underline;">
                                            {{{{ item.name }}}}{{{{ idx < props.row[field.key].length - 1 ? field.separator || ', ' : '' }}}}
                                        </a>
                                    </template>
                                    <template v-else>
                                        <span :class="item.approved ? 'st-ok-strong' : 'st-pending'">
                                            {{{{ item.name }}}}{{{{ idx < props.row[field.key].length - 1 ? field.separator || ', ' : '' }}}}
                                        </span>
                                    </template>
                                    <q-btn v-if="(field.key === 'commentators' || field.key === 'trackers') && !{'true' if admin_controls else 'false'} && item.approved && !item.acknowledged && item.discord_id == field.discord_id"
                                           icon="check" color="primary" size="xs" dense flat
                                           @click="$parent.$emit('acknowledge_' + field.key.slice(0, -1), {{ row: props.row, idx }})">
                                        <q-tooltip>Acknowledge</q-tooltip>
                                    </q-btn>
                                </span>
                            </template>
                        </template>
                        <template v-else>{{{{ props.row[field.key] }}}}</template>
                    </span>
                </template>

                <!-- For state field with admin buttons -->
                <template v-else-if="field.stateField">
                    <!-- Scheduled state: show Check In button -->
                    <q-btn v-if="{'true' if admin_controls else 'false'} && props.row[field.key] === 'Scheduled'"
                           @click="$parent.$emit('seat', {{ key: props.row.id }})"
                           icon="chair" color="primary" size="sm"
                           style="margin-bottom: 8px;">
                        Check In
                    </q-btn>

                    <!-- Checked In: show Start button and timestamp -->
                    <div v-else-if="{'true' if admin_controls else 'false'} && props.row[field.key] === 'Checked In'"
                         style="display: flex; flex-direction: column; gap: 4px;">
                        <q-btn @click="$parent.$emit('start', {{ key: props.row.id }})"
                               icon="play_arrow" color="primary" size="sm">
                            Start
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="check" class="st-neutral" size="xs" />
                            <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                        </div>
                    </div>

                    <!-- Started: show Finish button and timestamp -->
                    <div v-else-if="{'true' if admin_controls else 'false'} && props.row[field.key] === 'Started'"
                         style="display: flex; flex-direction: column; gap: 4px;">
                        <q-btn @click="$parent.$emit('finish', {{ key: props.row.id }})"
                               icon="sports_score" color="primary" size="sm">
                            Finish
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="play_arrow" class="st-live" size="xs" />
                            <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                        </div>
                    </div>

                    <!-- Finished: show Confirm button and timestamp -->
                    <div v-else-if="{'true' if admin_controls else 'false'} && props.row[field.key] === 'Finished'"
                         style="display: flex; flex-direction: column; gap: 4px;">
                        <q-btn @click="$parent.$emit('confirm', {{ key: props.row.id }})"
                               icon="check_circle" color="primary" size="sm">
                            Confirm
                        </q-btn>
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="flag" class="st-pending" size="xs" />
                            <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                        </div>
                    </div>

                    <!-- Confirmed: show state with icon and timestamp -->
                    <div v-else-if="props.row[field.key] === 'Confirmed'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="verified" class="st-ok" size="sm" />
                            <span style="font-weight: 500;">{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>

                    <!-- Non-admin views: show state with icon and timestamp -->
                    <div v-else-if="props.row[field.key] === 'Finished'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="flag" class="st-pending" size="sm" />
                            <span>{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                    <div v-else-if="props.row[field.key] === 'Started'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="play_arrow" class="st-live" size="sm" />
                            <span>{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                    <div v-else-if="props.row[field.key] === 'Checked In'" style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="check" class="st-neutral" size="sm" />
                            <span>{{{{ props.row[field.key] }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>

                    <!-- Fallback for Scheduled or other states -->
                    <div v-else style="display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; align-items: center; gap: 4px;">
                            <q-icon name="schedule" class="st-neutral" size="sm" />
                            <span>{{{{ props.row[field.key] || 'Scheduled' }}}}</span>
                        </div>
                        <span class="cell-timestamp">{{{{ props.row.state_timestamp }}}}</span>
                    </div>
                </template>

                <!-- For generated_seed field, truncate long URLs -->
                <template v-else-if="field.key === 'generated_seed'">
                    <!-- Show generate button if admin, has seed generator, and no seed yet -->
                    <q-btn v-if="{'true' if admin_controls else 'false'} && props.row.tournament_seed_generator && !props.row[field.key]"
                           :loading="props.row._generating_seed"
                           :disabled="props.row._generating_seed"
                           @click="(props.row._generating_seed = true, $parent.$emit('roll', {{ key: props.row.id }}))"
                           icon="casino" color="primary" size="sm"
                           style="margin-bottom: 8px;">
                        Generate Seed
                    </q-btn>
                    <template v-if="props.row[field.key]">
                        <a v-if="props.row[field.key].startsWith('https://') || props.row[field.key].startsWith('http://')"
                           :href="props.row[field.key]" target="_blank" style="color: var(--sgl-link); text-decoration: underline;">
                            {{{{ props.row[field.key].length > 40 ? props.row[field.key].substring(0, 40) + '...' : props.row[field.key] }}}}
                        </a>
                        <span v-else>
                            {{{{ props.row[field.key].length > 40 ? props.row[field.key].substring(0, 40) + '...' : props.row[field.key] }}}}
                        </span>
                    </template>
                    <template v-else-if="!{'true' if admin_controls else 'false'} || !props.row.tournament_seed_generator">-</template>
                </template>

                <!-- Acknowledgments field: icon + name per player -->
                <template v-else-if="field.ackField">
                    <template v-if="Array.isArray(props.row[field.key])">
                        <div v-for="(item, idx) in props.row[field.key]" :key="idx"
                             style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
                            <q-icon :name="item.acknowledged ? 'check_circle' : 'schedule'"
                                    :class="item.acknowledged ? 'st-ok' : 'st-pending'" size="xs" />
                            <span :class="item.acknowledged ? 'st-ok-strong' : 'st-pending'">
                                {{{{ item.name }}}}<span v-if="item.acknowledged && item.auto" style="font-style: italic; font-weight: normal;"> (auto)</span>
                            </span>
                        </div>
                    </template>
                    <template v-else>—</template>
                </template>

                <!-- Watch toggle (logged-in users only) -->
                <template v-else-if="field.watchField">
                    <q-btn :icon="props.row._watching ? 'visibility' : 'visibility_off'"
                           :color="props.row._watching ? 'primary' : 'grey'"
                           size="sm" flat round
                           @click="$parent.$emit('toggle_watch', props.row)">
                        <q-tooltip>{{{{ props.row._watching ? 'Stop watching this match' : 'Watch this match for Discord updates' }}}}</q-tooltip>
                    </q-btn>
                </template>

                <!-- For stream_room field with admin button -->
                <template v-else-if="field.key === 'stream_room'">
                    <a v-if="props.row[field.key] && props.row.stream_room_url" :href="props.row.stream_room_url" target="_blank" rel="noopener noreferrer" style="color: var(--sgl-link); text-decoration: underline;">{{{{ props.row[field.key] }}}}</a>
                    <span v-else-if="props.row[field.key]">{{{{ props.row[field.key] }}}}</span>
                    <span v-if="props.row.is_stream_candidate && !props.row[field.key]" class="sgl-chip sgl-chip--candidate q-ml-xs">candidate</span>
                    <q-btn v-if="{'true' if (admin_controls and can_crud) else 'false'} && !props.row[field.key]"
                           @click="$parent.$emit('edit-stream-room', {{ key: props.row.id }})"
                           icon="movie" color="primary" size="sm"
                           style="margin-bottom: 8px;">
                        Assign Stage
                    </q-btn>
                    <template v-if="!props.row[field.key] && !props.row.is_stream_candidate && !{'true' if (admin_controls and can_crud) else 'false'}">-</template>
                </template>

                <!-- Default rendering for other fields -->
                <template v-else>
                    {{{{ props.row[field.key] || '' }}}}
                </template>
            </div>
        </div>
        </div>
        ''')
