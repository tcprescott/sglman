"""The drawer's Qualifiers item: offered to members where the flag is live, and nowhere else.

Before it existed nothing in the app linked to /qualifiers, so a player could only
arrive by typing the URL or tapping a DM.
"""

import pytest

from application.services import FeatureFlagService
from application.tenant_context import tenant_scope
from models import FeatureFlag, Role, TenantMembership, User, UserRole
from theme.base import BaseLayout

pytestmark = pytest.mark.anyio


async def _prepared(user) -> BaseLayout:
    with tenant_scope(1):
        return await BaseLayout(user=user).prepare()


async def test_a_member_gets_the_item_when_qualifiers_are_live(db):
    member = await User.create(discord_id=900901, username='member')
    await TenantMembership.create(user=member, tenant_id=1)

    assert (await _prepared(member))._show_qualifiers is True


async def test_a_non_member_and_a_signed_out_visitor_do_not(db):
    stranger = await User.create(discord_id=900902, username='stranger')

    assert (await _prepared(stranger))._show_qualifiers is False
    assert (await _prepared(None))._show_qualifiers is False


async def test_the_item_goes_when_the_community_turns_qualifiers_off(db):
    staff = await User.create(discord_id=900903, username='staff')
    await UserRole.create(user=staff, role=Role.STAFF, tenant_id=1)
    await TenantMembership.create(user=staff, tenant_id=1)
    with tenant_scope(1):
        await FeatureFlagService().set_tenant_enabled(staff, FeatureFlag.ASYNC_QUALIFIERS, False)

    assert (await _prepared(staff))._show_qualifiers is False
