#!/usr/bin/env python3
"""Force a dev tenant's feature flags on or off — the knob the flag sweep turns.

Feature gating is two-sided: an entry surface hides a disabled feature and the
owning service *refuses* it. The failure mode that costs a page is an **ungated**
surface (the Profile tab, an admin table, a dialog) that calls a gated service
anyway — fine on a tenant that has the feature, a ``FeatureDisabledError`` and a
dead section on one that doesn't. Nothing in the Python suite renders those
pages, so the way to catch it is to drive the real app with flags off; this
script sets that state, and ``scripts/ui_flag_sweep.sh`` drives the browser.

Writes per-tenant availability/enable overrides directly (``TenantFeatureFlag``),
which is what the ``/platform`` + admin Features surfaces resolve through, so the
running app picks the change up on its next request — no restart. Dev only.

    poetry run python scripts/set_feature_flags.py --tenant default --show
    poetry run python scripts/set_feature_flags.py --tenant default --off all --snapshot /tmp/flags.json
    poetry run python scripts/set_feature_flags.py --tenant default --on challonge,brackets
    poetry run python scripts/set_feature_flags.py --tenant default --restore /tmp/flags.json
    poetry run python scripts/set_feature_flags.py --tenant default --clear all

``--snapshot`` records the tenant's current override rows before mutating;
``--restore`` puts exactly those rows back (the safe way to end a sweep, since
``--clear`` would also drop the demo overrides ``seed_dev.py`` sets up).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from tortoise import Tortoise

from application.services.feature_flag_service import FeatureFlagService
from application.tenant_context import tenant_scope
from models import FeatureFlag, Tenant, TenantFeatureFlag

ALL = 'all'


def parse_flags(raw: str) -> List[FeatureFlag]:
    if raw.strip().lower() == ALL:
        return list(FeatureFlag)
    flags = []
    for key in (part.strip() for part in raw.split(',') if part.strip()):
        try:
            flags.append(FeatureFlag(key))
        except ValueError:
            valid = ', '.join(f.value for f in FeatureFlag)
            print(f"Unknown feature flag {key!r}. Valid keys: {valid}")
            sys.exit(2)
    return flags


async def snapshot(tenant: Tenant, path: Path) -> None:
    rows = await TenantFeatureFlag.filter(tenant_id=tenant.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'tenant': tenant.slug,
        'overrides': [
            {'flag': r.flag, 'available': r.available, 'enabled': r.enabled} for r in rows
        ],
    }, indent=2))
    print(f"  snapshot: {len(rows)} override row(s) -> {path}")


async def restore(tenant: Tenant, path: Path) -> None:
    data = json.loads(path.read_text())
    if data.get('tenant') != tenant.slug:
        print(f"Snapshot is for tenant {data.get('tenant')!r}, not {tenant.slug!r}.")
        sys.exit(2)
    await TenantFeatureFlag.filter(tenant_id=tenant.id).delete()
    for row in data['overrides']:
        await TenantFeatureFlag.create(
            tenant_id=tenant.id, flag=row['flag'],
            available=row['available'], enabled=row['enabled'],
        )
    print(f"  restored {len(data['overrides'])} override row(s) from {path}")


async def set_flags(tenant: Tenant, flags: List[FeatureFlag], value: Optional[bool]) -> None:
    """Force ``flags`` on (True), off (False), or back to the tier (None)."""
    for flag in flags:
        if value is None:
            await TenantFeatureFlag.filter(tenant_id=tenant.id, flag=flag.value).delete()
        else:
            await TenantFeatureFlag.update_or_create(
                tenant_id=tenant.id, flag=flag.value,
                defaults={'available': value, 'enabled': value},
            )
    word = {True: 'forced on', False: 'forced off', None: 'cleared (inherits tier)'}[value]
    print(f"  {len(flags)} flag(s) {word} for '{tenant.slug}'")


async def show(tenant: Tenant) -> None:
    service = FeatureFlagService()
    with tenant_scope(tenant.id):
        live = await service.enabled_flags()
    print(f"  live flags for '{tenant.slug}':")
    for flag in FeatureFlag:
        print(f"    {'ON ' if flag in live else 'off'}  {flag.value}")


async def main(args: argparse.Namespace) -> None:
    from migrations.tortoise_config import TORTOISE_ORM

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        tenant = await Tenant.get_or_none(slug=args.tenant)
        if tenant is None:
            print(f"No tenant with slug {args.tenant!r}. Seed one first (scripts/seed_dev.py).")
            sys.exit(1)
        if args.snapshot:
            await snapshot(tenant, Path(args.snapshot))
        if args.restore:
            await restore(tenant, Path(args.restore))
        if args.on:
            await set_flags(tenant, parse_flags(args.on), True)
        if args.off:
            await set_flags(tenant, parse_flags(args.off), False)
        if args.clear:
            await set_flags(tenant, parse_flags(args.clear), None)
        if args.show or not (args.on or args.off or args.clear or args.restore or args.snapshot):
            await show(tenant)
    finally:
        await Tortoise.close_connections()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--tenant', default='default', help="tenant slug (default: 'default')")
    parser.add_argument('--on', help="flag keys to force available+enabled, or 'all'")
    parser.add_argument('--off', help="flag keys to force off, or 'all'")
    parser.add_argument('--clear', help="flag keys whose override to drop (inherit tier), or 'all'")
    parser.add_argument('--snapshot', help='write current override rows to this path before mutating')
    parser.add_argument('--restore', help='replace override rows with those in this snapshot file')
    parser.add_argument('--show', action='store_true', help='print the resulting live flag set')
    asyncio.run(main(parser.parse_args()))
