import pytest
from tortoise import Tortoise


@pytest.fixture(scope="session")
async def db():
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["models"]},
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()
