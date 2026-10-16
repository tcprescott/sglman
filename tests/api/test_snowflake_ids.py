"""Discord ids leave the API as strings and arrive as either form.

A snowflake is past 2**53, so a JSON number loses its last digits in any
JavaScript client.
"""

from api.schemas.discord_role_mappings import DiscordRoleMappingCreate, DiscordRoleMappingResponse
from api.schemas.users import UserListItem

SNOWFLAKE = 320395696098377729


def test_user_discord_id_serializes_as_string():
    item = UserListItem(id=1, username='a', discord_id=SNOWFLAKE, is_active=True)
    assert f'"discord_id":"{SNOWFLAKE}"' in item.model_dump_json()


def test_requests_accept_string_or_number():
    for value in (str(SNOWFLAKE), SNOWFLAKE):
        body = DiscordRoleMappingCreate.model_validate(
            {'guild_id': value, 'discord_role_id': value, 'discord_role_name': 'r', 'app_role': 'staff'}
        )
        assert body.guild_id == SNOWFLAKE and body.discord_role_id == SNOWFLAKE


def test_response_schema_documents_a_string():
    schema = DiscordRoleMappingResponse.model_json_schema(mode='serialization')
    assert schema['properties']['guild_id']['type'] == 'string'


def test_no_snowflake_field_is_a_bare_int():
    import importlib
    import json
    import pkgutil
    import re

    from pydantic import BaseModel

    import api.schemas

    modules = [importlib.import_module('mcpserver.schemas')] + [
        importlib.import_module(f'api.schemas.{m.name}') for m in pkgutil.iter_modules(api.schemas.__path__)
    ]
    name = re.compile(r'^(discord_\w*id|guild_id|channel_id|message_id)$')
    bare = []
    for module in modules:
        for obj in vars(module).values():
            if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
                continue
            for field in obj.model_fields:
                if not name.match(field):
                    continue
                prop = dict(obj.model_json_schema(mode='serialization')['properties'][field])
                prop.pop('description', None)
                if 'integer' in json.dumps(prop):
                    bare.append(f'{obj.__name__}.{field}')
    assert not bare, f'Use api.schemas.snowflake.Snowflake for: {sorted(set(bare))}'
