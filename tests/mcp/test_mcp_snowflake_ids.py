"""MCP sends Discord ids as strings so JavaScript clients can't round them."""

import json

from pydantic import BaseModel

import mcpserver.schemas
from mcpserver.schemas import UserSummary

SNOWFLAKE = 320395696098377729


def test_discord_id_serializes_as_string_and_accepts_either_form():
    for value in (SNOWFLAKE, str(SNOWFLAKE)):
        item = UserSummary.model_validate({'id': 1, 'username': 'a', 'discord_id': value})
        assert item.discord_id == SNOWFLAKE
        assert f'"discord_id":"{SNOWFLAKE}"' in item.model_dump_json()


def test_no_mcp_snowflake_field_serializes_as_a_number():
    snowflake_names = ('discord_id', 'guild_id', 'channel_id', 'message_id', 'discord_role_id', 'discord_event_id')
    bare = []
    for obj in vars(mcpserver.schemas).values():
        if not (isinstance(obj, type) and issubclass(obj, BaseModel)) or obj is BaseModel:
            continue
        props = obj.model_json_schema(mode='serialization').get('properties', {})
        for field in obj.model_fields:
            if field in snowflake_names:
                prop = dict(props[field])
                prop.pop('description', None)
                if 'integer' in json.dumps(prop):
                    bare.append(f'{obj.__name__}.{field}')
    assert not bare, f'Use mcpserver.snowflake.Snowflake for: {sorted(set(bare))}'
