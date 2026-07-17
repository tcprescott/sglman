import pytest

# ``stub_discord_queue`` is defined suite-wide (autouse) in ``tests/conftest.py``.


# The permission-gate methods that the various service unit tests bypass so they
# can exercise business logic. Patching the union is safe: a method a given
# service never calls is simply never exercised, and denial-path tests override
# the specific gate they care about in-test (which wins over this fixture).
_ALLOW_GATES = (
    'is_staff',
    'is_tournament_admin',
    'can_edit_tournament',
    'can_crud_match',
    'can_transition_match',
    'can_assign_match_stream',
    'can_approve_crew',
    'can_manage_stream_rooms',
    'can_manage_volunteers',
    'can_grant_roles',
)


@pytest.fixture
def bypass_auth(monkeypatch):
    """Disable AuthService permission checks for service unit tests.

    Opt in per module with ``pytestmark = pytest.mark.usefixtures("bypass_auth")``
    (or request it directly). Tests exercising a *denied* path re-patch the
    specific gate to raise/deny, which overrides this fixture.
    """
    from application.services import auth_service

    async def allow(*_args, **_kwargs):
        return True

    async def noop_ensure(*_args, **_kwargs):
        return None

    for name in _ALLOW_GATES:
        monkeypatch.setattr(auth_service.AuthService, name, allow)
    monkeypatch.setattr(auth_service.AuthService, 'ensure', noop_ensure)
