"""Mirroring a Matcherino venue's badge sales into check-in rows.

The data half of :meth:`CheckInService.sync_event`: who the buyers are, and
the badge-type and badge rows behind them. The service owns the roster rows,
account matching, locking and audit around these.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from application.repositories import CheckInPassRepository, CheckInTierRepository
from application.utils.clients.matcherino_client import (
    MatcherinoAccount,
    MatcherinoPurchase,
    MatcherinoTier,
    VenueSales,
)
from models import CheckInEntrant, CheckInEvent, CheckInPass, CheckInTier


@dataclass
class Buyer:
    account: MatcherinoAccount
    holds_badge: bool = False
    first_bought: Optional[datetime] = None


def buyers_of(sales: VenueSales) -> Dict[str, Buyer]:
    """Every buyer by Matcherino user id, whether they still hold a badge, and
    when they bought their first one that wasn't refunded."""
    buyers: Dict[str, Buyer] = {}
    for purchase in sales.purchases:
        buyer = buyers.setdefault(purchase.buyer.user_id, Buyer(purchase.buyer))
        if not purchase.active:
            continue
        buyer.holds_badge = True
        if purchase.purchased_at and (buyer.first_bought is None or purchase.purchased_at < buyer.first_bought):
            buyer.first_bought = purchase.purchased_at
    return buyers


def buyer_fields(buyer: Buyer) -> Dict[str, object]:
    """The roster-row columns a sync owns, from the buyer's account."""
    account = buyer.account
    return {
        'display_name': account.display_name[:255],
        'avatar_url': (account.avatar_url or '')[:512] or None,
        'auth_provider': account.auth_provider,
        'auth_id': account.auth_id,
        'registered_at': buyer.first_bought,
        'source_data': account.raw,
    }


async def apply_tiers(
    repo: CheckInTierRepository, event: CheckInEvent, sales: VenueSales,
) -> Dict[int, CheckInTier]:
    """Upsert the venue's badge types, by Matcherino pass id.

    A badge type only seen embedded in a purchase (deleted from the venue since)
    still gets a row, so the badges sold under it have somewhere to point.
    """
    served: Dict[int, MatcherinoTier] = {tier.id: tier for tier in sales.tiers}
    for purchase in sales.purchases:
        served.setdefault(purchase.tier.id, purchase.tier)
    tiers = await repo.by_pass_id(event)
    for pass_id, tier in served.items():
        fields = {'title': tier.title[:255], 'amount_cents': tier.amount_cents, 'role': tier.role}
        row = tiers.get(pass_id)
        if row is None:
            tiers[pass_id] = await repo.create(event=event, matcherino_pass_id=pass_id, **fields)
            continue
        changes = [key for key, value in fields.items() if getattr(row, key) != value]
        if changes:
            row.update_from_dict({key: fields[key] for key in changes})
            await repo.save(row, [*changes, 'updated_at'])
    return tiers


async def apply_badges(
    repo: CheckInPassRepository,
    event: CheckInEvent,
    purchases: Sequence[MatcherinoPurchase],
    stored: Dict[int, CheckInPass],
    tiers: Dict[int, CheckInTier],
    rows: Dict[str, CheckInEntrant],
    now: datetime,
) -> None:
    """Upsert one badge row per purchase; mark the ones that left the feed removed."""
    created: List[CheckInPass] = []
    seen = set()
    for purchase in purchases:
        seen.add(purchase.id)
        entrant = rows.get(purchase.buyer.user_id)
        fields: Dict[str, object] = {
            'tier_id': tiers[purchase.tier.id].id,
            'entrant_id': entrant.id if entrant else None,
            'buyer_matcherino_user_id': purchase.buyer.user_id,
            'code': purchase.code[:32],
            'purchased_at': purchase.purchased_at,
            'refunded_at': purchase.refunded_at,
            'removed_at': None,
            'source_data': purchase.raw,
        }
        badge = stored.get(purchase.id)
        if badge is None:
            created.append(CheckInPass(event=event, matcherino_purchase_id=purchase.id, **fields))
            continue
        changes = [key for key, value in fields.items() if getattr(badge, key) != value]
        if changes:
            badge.update_from_dict({key: fields[key] for key in changes})
            await repo.save(badge, [*changes, 'updated_at'])
    if created:
        await repo.bulk_create(created)
    for purchase_id, badge in stored.items():
        if purchase_id not in seen and badge.removed_at is None:
            badge.removed_at = now
            await repo.save(badge, ['removed_at', 'updated_at'])
