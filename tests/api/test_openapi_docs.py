"""The /api/docs document: every endpoint says what it does and who can call it."""

from typing import Any, Dict, Iterator, Tuple

import pytest
from fastapi.routing import APIRoute, iter_route_contexts

from api.openapi_docs import TAG_GROUPS, WHO_CAN_CALL, api_description, install
from api.rate_limit import limit_per_minute
from application.events import EventType
from tests.api_helpers import build_api_app

# Routers still waiting on their write-up (done area by area in separate PRs).
# Remove each as it lands; delete the set and its two checks once it is empty.
PENDING_MODULES = {
    'api.routers.async_qualifier_live_races', 'api.routers.async_qualifiers',
    'api.routers.audit', 'api.routers.brackets', 'api.routers.check_in',
    'api.routers.crew', 'api.routers.discord_events', 'api.routers.discord_role_mappings',
    'api.routers.equipment', 'api.routers.feedback', 'api.routers.health',
    'api.routers.match_actions', 'api.routers.matches', 'api.routers.memberships',
    'api.routers.notifications', 'api.routers.payouts', 'api.routers.player_availability',
    'api.routers.presets', 'api.routers.race_room_profiles', 'api.routers.race_rooms',
    'api.routers.racetime_bots', 'api.routers.reports', 'api.routers.reschedule_requests',
    'api.routers.seeds', 'api.routers.service_health', 'api.routers.speedgaming',
    'api.routers.stage_actions', 'api.routers.stages', 'api.routers.system_config',
    'api.routers.telemetry', 'api.routers.tokens', 'api.routers.tournament_actions',
    'api.routers.tournaments', 'api.routers.triforce', 'api.routers.users',
    'api.routers.volunteers', 'api.routers.web_push', 'api.routers.webhooks',
}


def _spec() -> Dict[str, Any]:
    app = build_api_app()
    install(app)
    return app.openapi()


def _operations() -> Iterator[Tuple[str, str, str, Dict[str, Any]]]:
    """(module, method, path, operation) for every API endpoint in the document."""
    paths = _spec()['paths']
    for route in iter_route_contexts(build_api_app().routes):
        if not isinstance(route.original_route, APIRoute) or not route.include_in_schema:
            continue
        for method in sorted(route.methods):
            yield route.endpoint.__module__, method, route.path_format, paths[route.path_format][method.lower()]


def _is_untyped(response: Dict[str, Any]) -> bool:
    schema = response.get('content', {}).get('application/json', {}).get('schema')
    if schema is None:
        return False
    if any(key in schema for key in ('$ref', 'anyOf', 'oneOf', 'allOf', 'properties')):
        return False
    return schema.get('type', 'object') == 'object'


def test_every_endpoint_says_what_it_does_and_who_can_call_it():
    missing = [
        f'{method} {path} ({module})'
        for module, method, path, operation in _operations()
        if module not in PENDING_MODULES and WHO_CAN_CALL not in (operation.get('description') or '')
    ]
    assert not missing, (
        f'Give these routes a description= ending in "{WHO_CAN_CALL} ..." '
        '(see docs/reference/rest-api.md#documenting-an-endpoint):\n' + '\n'.join(missing)
    )


def test_every_json_response_has_a_schema():
    untyped = [
        f'{method} {path} -> {code}'
        for module, method, path, operation in _operations()
        if module not in PENDING_MODULES
        for code, response in operation['responses'].items()
        if code.startswith('2') and code != '204'
        and _is_untyped(response)
    ]
    assert not untyped, 'Give these routes a response_model:\n' + '\n'.join(untyped)


def test_every_section_is_declared_in_order():
    declared = [name for _, tags in TAG_GROUPS for name, _ in tags]
    assert len(declared) == len(set(declared))
    used = {tag for *_, operation in _operations() for tag in operation.get('tags', [])}
    assert used <= set(declared), f'Add these sections to TAG_GROUPS: {sorted(used - set(declared))}'
    assert [tag['name'] for tag in _spec()['tags']] == declared


def test_access_notes_follow_the_dependencies():
    paths = _spec()['paths']

    write = paths['/api/matches/{match_id}/crew']['post']
    assert "isn't read-only" in write['description']
    assert {'400', '401', '403', '404', '429'} <= set(write['responses'])

    read = paths['/api/matches']['get']
    assert "isn't read-only" not in (read.get('description') or '')
    assert '400' not in read['responses']

    gated = paths['/api/volunteers/shifts']['get']
    assert '**Volunteer Scheduling**' in gated['description']

    health = paths['/api/health']['get']
    assert 'not needed' in health['description']
    assert '401' not in health['responses']


def test_intro_states_the_rate_limit_and_token_scope():
    text = api_description()
    assert f'{limit_per_minute()} requests a minute' in text
    assert 'belongs to one community' in text
    assert '{rate_limit}' not in text


def test_webhooks_cover_every_deliverable_event():
    documented = set()
    for entry in _spec()['webhooks'].values():
        schema = entry['post']['requestBody']['content']['application/json']['schema']
        documented |= set(schema['properties']['event_type']['enum'])
    assert documented == EventType.ALL - {EventType.SERVICE_HEALTH_ALERT}


@pytest.mark.parametrize('module', sorted(PENDING_MODULES))
def test_pending_modules_exist(module):
    __import__(module)
