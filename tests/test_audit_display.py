"""The audit report's plain-language layer: labels, areas and the describer."""

import json

from application.services.audit_service import AuditActions
from application.utils.audit_display import (
    ACTION_LABELS,
    AREAS,
    AuditNames,
    action_label,
    actions_matching,
    area_by_key,
    area_for,
    describe,
)

ALL_ACTIONS = {v for k, v in vars(AuditActions).items() if k.isupper() and isinstance(v, str)}


def test_every_action_has_a_label_and_an_area():
    assert ALL_ACTIONS - set(ACTION_LABELS) == set()
    assert {a for a in ALL_ACTIONS if area_for(a) is None} == set()


def test_no_label_for_an_action_that_does_not_exist():
    assert set(ACTION_LABELS) - ALL_ACTIONS == set()


def test_prefixes_do_not_bleed_into_lookalike_actions():
    assert area_for('match.created').key == 'matches'
    assert area_for('matcherino_login.set').key == 'check_in'
    assert area_for('profile_nudge.dismissed').key == 'people'
    assert area_for('profile_nudges.updated').key == 'settings'
    assert area_for('tenant.join_requested').key == 'people'
    assert area_for('tenant.updated').key == 'settings'


def test_unknown_action_falls_back_to_a_tidy_key():
    assert action_label('widget.frobbed_hard') == 'Widget: frobbed hard'
    assert area_by_key('nope') is None
    assert {a.key for a in AREAS} >= {'matches', 'people', 'settings'}


def test_search_matches_labels_not_just_keys():
    assert 'match.stage_assigned' in actions_matching('stage')
    assert 'profile_nudge.dismissed' in actions_matching('REMINDER')
    assert actions_matching('   ') == []


def test_setting_change_shows_before_and_after_per_day():
    old = {'2026-10-22': {'open': '08:00', 'close': '23:00'}}
    new = {'2026-10-22': {'open': '08:00', 'close': '23:59'}}
    view = describe('system_config.updated', {
        'actor_discord_id': '185', 'actor_username': 'x', 'key': 'tournament_hours_by_date',
        'old_value': json.dumps(old), 'new_value': json.dumps(new),
    }, AuditNames())
    assert view.label == 'Changed a setting'
    assert view.area == 'Settings'
    assert [(c.field, c.before, c.after) for c in view.changes] == [('Thu Oct 22 · Close', '23:00', '23:59')]
    assert 'actor' not in ' '.join(k for k, _ in view.facts).lower()


def test_setting_saved_unchanged_says_so():
    view = describe('system_config.updated', {'key': 'max_concurrent_players', 'old_value': '40', 'new_value': '40'},
                    AuditNames())
    assert view.changes == []
    assert view.summary == 'Max concurrent players: saved unchanged'


def test_match_row_names_the_match_and_resolves_people():
    view = describe('match.rescheduled', {
        'changed_fields': ['tournament_id', 'scheduled_at', 'comment'], 'match_id': 1,
        'player_ids': [5, 6], 'commentator_ids': [], 'tracker_ids': [],
    }, AuditNames(users={5: 'Ana', 6: 'Bo'}))
    assert view.subject == 'Match #1'
    assert view.match_id == 1
    assert view.summary == 'Match #1 · Changed tournament, start time and comment'
    assert ('Players', 'Ana, Bo') in view.facts


def test_previous_value_pairs_become_a_change():
    view = describe('accommodation.status_changed', {
        'previous_status': 'acknowledged', 'status': 'arranged', 'request_id': 3, 'user_id': 101,
    }, AuditNames(users={101: 'Zed'}), actor_id=1)
    assert [(c.field, c.before, c.after) for c in view.changes] == [('Status', 'acknowledged', 'arranged')]
    assert view.summary == 'Zed · Status: acknowledged → arranged'


def test_own_profile_edit_does_not_repeat_the_actor_as_subject():
    view = describe('user.self_profile_updated', {'changed_fields': {'pronouns': 'he/him'}, 'target_user_id': 30},
                    AuditNames(users={30: 'Pat'}), actor_id=30)
    assert view.subject == ''
    assert view.summary == 'Pronouns: he/him'


def test_unresolved_stage_never_shows_a_name():
    view = describe('match.stage_assigned', {'match_id': 1, 'stage_id': 7}, AuditNames())
    assert ('Stage', 'Stage #7') in view.facts


def test_legacy_plain_text_details():
    view = describe('match.created', 'created by hand', AuditNames())
    assert view.summary == 'created by hand'
    assert view.raw == 'created by hand'
