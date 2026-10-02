"""Ids in public URLs: anything that cannot name a row is a not-found, not a crash.

``/brackets/abc`` answered FastAPI's raw 422 JSON, and ``/brackets/99999999999``
reached Postgres as a value an ``INT`` column cannot hold — a 500 and a Sentry
event for every mistyped spectator link.
"""

import pytest

from application.utils.route_params import MAX_INT_ID, parse_route_id


@pytest.mark.parametrize('raw, expected', [
    ('1', 1),
    ('42', 42),
    (str(MAX_INT_ID), MAX_INT_ID),
    (7, 7),
])
def test_a_real_id_parses(raw, expected):
    assert parse_route_id(raw) == expected


@pytest.mark.parametrize('raw', [
    'abc', '1a', '', ' 1', '1 ', '-1', '+1', '0', '1.0', '1e3', '١٢',
    str(MAX_INT_ID + 1), '99999999999999999999', None, True, 0, -5, MAX_INT_ID + 1,
])
def test_anything_else_is_none(raw):
    assert parse_route_id(raw) is None
