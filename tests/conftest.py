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
