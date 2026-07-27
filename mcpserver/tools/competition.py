"""Bracket and async-qualifier reads.

Both domains are behind per-tenant feature flags, so these tools also serve as
the working proof that the flag path behaves: a community without the flag gets
`not_found`, identical to asking for a bracket that does not exist, rather than
a message confirming the feature exists but is switched off.
"""

from typing import List

from mcp.server.fastmcp import FastMCP

from application.services import BracketService
from application.services.async_qualifier.async_qualifier_service import (
    AsyncQualifierService,
)
from mcpserver.auth import Gate, current_actor
from mcpserver.registry import register
from mcpserver.schemas import TenantArg
from models import FeatureFlag


async def list_brackets(
    tournament_id: int,
    tenant: TenantArg = None,
) -> List[dict]:
    """List a tournament's brackets."""
    brackets = await BracketService().list_brackets(tournament_id)
    return [
        {
            'id': b.id,
            'name': b.name,
            'format': getattr(b.format, 'value', b.format),
            'state': getattr(b.state, 'value', b.state),
        }
        for b in brackets
    ]


async def get_bracket_standings(
    bracket_id: int,
    tenant: TenantArg = None,
) -> List[dict]:
    """Get current standings for a bracket, grouped as the bracket format defines."""
    groups = await BracketService().standings(bracket_id)
    return [
        {
            'group': getattr(group, 'name', None),
            'rows': [
                {
                    'rank': getattr(row, 'rank', None),
                    'entrant': getattr(row, 'label', None) or getattr(row, 'name', None),
                    'wins': getattr(row, 'wins', None),
                    'losses': getattr(row, 'losses', None),
                }
                for row in getattr(group, 'rows', [])
            ],
        }
        for group in groups
    ]


async def list_async_qualifiers(
    tenant: TenantArg = None,
) -> List[dict]:
    """List the community's async qualifiers."""
    actor = current_actor()
    qualifiers = await AsyncQualifierService().list_qualifiers(actor.user)
    return [
        {
            'id': q.id,
            'name': q.name,
            'active': getattr(q, 'active', None),
            'tournament_id': q.tournament_id,
        }
        for q in qualifiers
    ]


def register_tools(mcp: FastMCP) -> None:
    register(
        mcp, list_brackets, gate=Gate.ACTOR,
        feature=FeatureFlag.BRACKETS, title='List brackets',
    )
    register(
        mcp, get_bracket_standings, gate=Gate.ACTOR,
        feature=FeatureFlag.BRACKETS, title='Bracket standings',
    )
    register(
        mcp, list_async_qualifiers, gate=Gate.ACTOR,
        feature=FeatureFlag.ASYNC_QUALIFIERS, title='List async qualifiers',
    )
