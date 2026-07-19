import pytest
from tortoise import Tortoise
from tortoise.models import Model

import models as _models
from application.tenant_context import require_tenant_id, set_tenant_id, reset_tenant_id

# Every DB-backed test runs inside a single default tenant. Because the default
# Tenant is the first row inserted into the fresh in-memory schema, its id is 1,
# which matches the ambient context set by ``_tenant_context`` below.
DEFAULT_TEST_TENANT_ID = 1


def _scoped_models() -> list[type[Model]]:
    """Every model carrying a ``tenant`` FK (scoped or nullable-tenant)."""
    return [
        obj for obj in vars(_models).values()
        if isinstance(obj, type) and issubclass(obj, Model) and obj is not Model
        and 'tenant' in obj._meta.fields_map
    ]


@pytest.fixture(autouse=True)
def _tenant_context():
    """Bind the default tenant for every test so ``require_tenant_id()`` resolves.

    DB-backed tests get the real default ``Tenant`` (id 1) created by the ``db``
    fixture; pure-mock tests just need *some* ambient id (their repositories are
    mocked, so the value is never used against a real query). Leak/isolation
    tests override this with explicit ``tenant_scope`` blocks.
    """
    token = set_tenant_id(DEFAULT_TEST_TENANT_ID)
    try:
        yield
    finally:
        reset_tenant_id(token)


@pytest.fixture
def app():
    """The full REST API app (all routers under ``/api``).

    Hoisted here from the ~19 API test modules that re-pasted it. The two
    hand-built apps (``test_api_matches.py`` / ``test_api_tokens.py``) keep
    their own bespoke fixtures.
    """
    from tests.api_helpers import build_api_app
    return build_api_app()


@pytest.fixture(autouse=True)
def stub_discord_queue(monkeypatch):
    """Capture coroutines handed to ``discord_queue.enqueue`` without running them.

    Discord notifications/DMs are fire-and-forget via the queue worker, so
    services only enqueue the coroutine — they never await it. Capturing and
    closing the coroutines lets tests assert the call happened while avoiding
    'coroutine was never awaited' warnings. Applied suite-wide; the handful of
    tests that need the *real* enqueue (``tests/services/test_discord_queue.py``)
    restore it explicitly with their own ``monkeypatch``.
    """
    captured = []
    monkeypatch.setattr(
        'application.services.discord_queue.enqueue', captured.append
    )
    yield captured
    for coro in captured:
        coro.close()


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """Fail loudly when a test touches the real network.

    The suite must behave identically offline and in CI (a service-health test
    once POSTed to five third-party production hosts on every CI run). Loopback
    stays allowed so tests may drive a locally-bound server; httpx's
    ASGITransport and the in-memory DB never open sockets at all.
    """
    import socket

    real_connect = socket.socket.connect
    loopback = ('127.0.0.1', '::1', 'localhost', '0.0.0.0')

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, (bytes, bytearray)):
            host = host.decode(errors='replace')
        if self.family == socket.AF_UNIX or host in loopback:
            return real_connect(self, address)
        raise RuntimeError(
            f'External network access blocked in tests: connect to {address!r}. '
            f'Mock the client (MOCK_* helpers) or stub the transport instead.'
        )

    monkeypatch.setattr(socket.socket, 'connect', guarded_connect)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Isolate the process-global API rate-limiter counters per test.

    The limiter keys unauthenticated requests by client IP, which would
    otherwise accumulate across the whole suite and spuriously trip 429s.
    """
    from api.rate_limit import _hits
    _hits.clear()
    yield
    _hits.clear()


@pytest.fixture
async def db(monkeypatch):
    """Function-scoped in-memory SQLite for tests that need a real DB.

    Each test gets a fresh schema with no leakage from prior tests. A single
    default ``Tenant`` (id 1) is created up front, and every tenant-scoped
    model's ``.create`` is wrapped to stamp that tenant when a caller omits it —
    so the existing ~700 ``Model.create`` test sites need no per-call edits while
    the production ``never auto-stamp`` contract stays intact (that wrapper lives
    only here, in the test harness). Repositories that stamp tenant themselves
    pass ``tenant_id`` explicitly, which the wrapper leaves untouched.
    """
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()

    await _models.Tenant.create(
        id=DEFAULT_TEST_TENANT_ID, name='Default', slug='default',
    )

    # Feature flags default OFF (available AND enabled), which would make every
    # flag-gated service guard raise for the ~all-features-on legacy test suite.
    # Turn every flag fully on for the default tenant so existing tests exercise
    # features as before; feature-flag-specific tests set their own state under
    # their own tenants.
    for flag in _models.FeatureFlag:
        await _models.TenantFeatureFlag.create(
            tenant_id=DEFAULT_TEST_TENANT_ID, flag=flag.value,
            available=True, enabled=True,
        )

    for model in _scoped_models():
        original = model.create

        def _make(original):
            async def _stamped_create(**kwargs):
                # Stamp the currently-scoped tenant (default id 1, or whatever a
                # leak test set via tenant_scope) so direct test creates land in
                # the right tenant without a per-call edit.
                if 'tenant' not in kwargs and 'tenant_id' not in kwargs:
                    kwargs['tenant_id'] = require_tenant_id()
                return await original(**kwargs)
            return _stamped_create

        monkeypatch.setattr(model, 'create', _make(original))

    try:
        yield
    finally:
        await Tortoise.close_connections()


# Canonical two-tenant fixtures. Historically each isolation test re-created a
# second tenant inline under one of four drifting slugs (``tenant-b``/``beta``/
# ``b``/``community``); these fixtures give one slug convention (``tenant-b``)
# and one place to build on. ``tenant_a`` is the default tenant (id 1) the
# ``db`` fixture creates.
SECOND_TENANT_SLUG = 'tenant-b'


@pytest.fixture
async def two_tenants(db):
    """The default tenant plus a second one (slug ``tenant-b``).

    Returns ``(tenant_a, tenant_b)``. Build tenant-scoped rows on top with
    ``tenant_scope(tenant.id)``.
    """
    tenant_a = await _models.Tenant.get(id=DEFAULT_TEST_TENANT_ID)
    tenant_b = await _models.Tenant.create(name='Tenant B', slug=SECOND_TENANT_SLUG)
    return tenant_a, tenant_b


@pytest.fixture
async def two_tenant_api(two_tenants):
    """Two tenants each with a STAFF token, a tournament, and a match, plus an API app.

    Returns a dict: ``app``, ``token_a``/``token_b``, ``ta``/``tb``, ``ma``/``mb``.
    """
    from application.tenant_context import tenant_scope
    from models import Match, Role, Tournament
    from tests.api_helpers import build_api_app, create_user_token

    tenant_a, tenant_b = two_tenants
    with tenant_scope(tenant_a.id):
        _, token_a = await create_user_token(username='a-staff', roles=[Role.STAFF])
        ta = await Tournament.create(name='A Cup')
        ma = await Match.create(tournament=ta)
    with tenant_scope(tenant_b.id):
        _, token_b = await create_user_token(username='b-staff', roles=[Role.STAFF])
        tb = await Tournament.create(name='B Cup')
        mb = await Match.create(tournament=tb)

    return {
        'app': build_api_app(),
        'token_a': token_a, 'token_b': token_b,
        'ta': ta, 'tb': tb, 'ma': ma, 'mb': mb,
    }
