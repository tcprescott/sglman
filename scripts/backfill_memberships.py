#!/usr/bin/env python3
"""Give every tenant-scoped role-holder a ``TenantMembership``.

Run from the project root:
    poetry run python scripts/backfill_memberships.py [--dry-run]

The invariant is *"holding any role in a tenant implies membership in that
tenant"*, now enforced wherever roles are written. Roles granted before that —
through the Users tab or the Discord role sync, both of which wrote a role and
no membership — need catching up once.

``SUPER_ADMIN`` is skipped: its ``UserRole`` carries ``tenant=NULL`` and it
belongs to no community.

Idempotent and safe to re-run; the membership gate's go/no-go audit re-runs it.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tortoise import Tortoise

from models import Role, TenantMembership, UserRole


async def find_gaps() -> list[tuple[int, int]]:
    """``(user_id, tenant_id)`` pairs holding a role with no membership."""
    rows = await UserRole.filter(tenant_id__not_isnull=True).exclude(role=Role.SUPER_ADMIN)
    wanted = {(r.user_id, r.tenant_id) for r in rows}
    existing = {
        (m.user_id, m.tenant_id)
        for m in await TenantMembership.filter(
            user_id__in=[u for u, _ in wanted] or [0],
        )
    }
    return sorted(wanted - existing)


async def backfill(dry_run: bool = False) -> int:
    gaps = await find_gaps()
    if not gaps:
        print('No gaps: every tenant-scoped role-holder is already a member.')
        return 0
    print(f'{len(gaps)} role-holder(s) with no membership:')
    for user_id, tenant_id in gaps:
        print(f'  user={user_id} tenant={tenant_id}')
    if dry_run:
        print('--dry-run: nothing written.')
        return len(gaps)
    for user_id, tenant_id in gaps:
        await TenantMembership.get_or_create(user_id=user_id, tenant_id=tenant_id)
    print(f'Wrote {len(gaps)} membership row(s).')
    return len(gaps)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='report without writing')
    args = parser.parse_args()

    # Lazy, so importing this module stays env-free: load_dotenv() at import
    # time pushes the dev .env into os.environ for whatever process imports it.
    from dotenv import load_dotenv
    load_dotenv()

    from migrations.tortoise_config import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await backfill(dry_run=args.dry_run)
    finally:
        await Tortoise.close_connections()


if __name__ == '__main__':
    asyncio.run(main())
