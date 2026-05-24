import pytest
from tortoise import Tortoise


@pytest.fixture
async def db():
    """Function-scoped in-memory SQLite for tests that need a real DB.

    Each test gets a fresh schema with no leakage from prior tests.
    """
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise._drop_databases()
        await Tortoise.close_connections()
