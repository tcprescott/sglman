"""The bracket-API fixtures the bracket REST test modules share.

Four modules drive these endpoints — ``test_brackets`` (the happy path and the
auth matrix), ``test_brackets_management`` (editing, rounds, seeds, overrides),
``test_brackets_standings`` (standings and the advance dry run) and
``test_brackets_game_link`` (attaching a manual match) — because one module of
all of it ran past the file-length guideline.

The setup helpers live here rather than being copied per module: the first split
copied them, and a fixture that says "enroll these names and hand back their
entry ids" has to mean the same thing in every module asserting on those ids.
"""

from application.services.api_token_service import ApiTokenService
from models import Role, Tournament
from tests.api_helpers import create_user_token


async def staff_token(username='staff'):
    return await create_user_token(username=username, roles=[Role.STAFF])


async def tournament(name='Cup'):
    return await Tournament.create(name=name)


async def token_for(user):
    """A write token for an already-created user (not a freshly-made one)."""
    _, raw = await ApiTokenService().create_token(user, name='test')
    return raw


async def draft(c, tourney, **kwargs):
    """Create a DRAFT bracket on ``tourney`` and return its id."""
    payload = {
        'tournament_id': tourney.id, 'name': 'Main', 'format': 'single_elim',
    }
    payload.update(kwargs)
    return (await c.post('/api/brackets', json=payload)).json()['id']


async def enroll(c, bracket_id, tourney, names, *, user_ids=()):
    """Add each name as an entrant and enroll it; returns the entry ids in order."""
    entry_ids = []
    for i, name in enumerate(names):
        body = {'tournament_id': tourney.id, 'display_name': name}
        if user_ids:
            body['user_id'] = user_ids[i]
        entrant = (await c.post('/api/brackets/entrants', json=body)).json()
        entry_ids.append((await c.post(
            f'/api/brackets/{bracket_id}/entries', json={'entrant_id': entrant['id']},
        )).json()['id'])
    return entry_ids
