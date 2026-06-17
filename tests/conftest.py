import pytest
from tortoise import Tortoise


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
async def db():
    """Function-scoped in-memory SQLite for tests that need a real DB.

    Each test gets a fresh schema with no leakage from prior tests. Closing
    the in-memory connection at the end discards all rows; the next test
    re-runs ``Tortoise.init`` and ``generate_schemas`` to start clean.
    """
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()
