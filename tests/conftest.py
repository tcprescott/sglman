import pytest
from tortoise import Tortoise


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
