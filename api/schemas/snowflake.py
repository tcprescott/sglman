"""Discord snowflake ids as they cross the API and MCP boundary.

A snowflake is a 64-bit integer, past the 2**53 that a JSON number survives in
JavaScript: `JSON.parse` rounds `320395696098377729` to `320395696098377700`.
So output is always a decimal string, the same choice Discord's own API makes.
Input still accepts a plain number as well as a string, so existing callers keep
working; only the string form is safe from a JavaScript client.
"""

from typing import Annotated

from pydantic import PlainSerializer, WithJsonSchema

_PATTERN = r'^[0-9]{1,20}$'

Snowflake = Annotated[
    int,
    PlainSerializer(str, return_type=str, when_used='json'),
    WithJsonSchema(
        {'anyOf': [{'type': 'string', 'pattern': _PATTERN}, {'type': 'integer'}]},
        mode='validation',
    ),
    WithJsonSchema({'type': 'string', 'pattern': _PATTERN}, mode='serialization'),
]
