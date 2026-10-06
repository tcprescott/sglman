from typing import Optional

from tortoise import fields
from tortoise.models import Model

from .enums import CheckInEntrantSource, CheckInEventStatus, CheckInLinkMethod


class CheckInEvent(Model):
    """An in-person event whose attendees are checked in at a desk.

    Registration happens on Matcherino: ``matcherino_venue_id`` names the
    ticketed venue whose badge sales are mirrored into :class:`CheckInPass`
    rows, one :class:`CheckInEntrant` per buyer. It is nullable so an event can
    run on walk-ups alone. The sync bookkeeping
    (``last_synced_at``/``last_sync_error``/``last_sync_count``) is shown at the
    desk because the Matcherino endpoints are unofficial: when they break, the
    volunteers need to see that the roster is stale.
    """

    id = fields.IntField(pk=True)
    tenant: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.Tenant', related_name='check_in_events', on_delete=fields.CASCADE,
    )
    tenant_id: int
    name = fields.CharField(max_length=255)
    matcherino_venue_id = fields.IntField(null=True)
    status = fields.CharEnumField(CheckInEventStatus, default=CheckInEventStatus.DRAFT, max_length=16)
    sync_interval_minutes = fields.IntField(default=5)
    last_synced_at = fields.DatetimeField(null=True)
    last_sync_error = fields.TextField(null=True)
    last_sync_count = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    entrants: fields.ReverseRelation["CheckInEntrant"]
    tiers: fields.ReverseRelation["CheckInTier"]
    passes: fields.ReverseRelation["CheckInPass"]

    class Meta:
        table = 'checkinevent'
        unique_together = (('tenant', 'matcherino_venue_id'),)


class CheckInEntrant(Model):
    """One person on a check-in event's roster.

    A ``MATCHERINO`` row is a badge buyer, keyed by ``matcherino_user_id``,
    with the identity Matcherino served on their purchase; a ``WALK_UP`` row
    was added by staff at the desk. ``user`` is the matched Wizzrobe account,
    which is a nice-to-have rather than a requirement — plenty of buyers have
    none.

    ``source_data`` is the buyer's Matcherino account object as last served,
    kept so a field nothing reads yet can be backfilled from rows already
    synced. ``registered_at`` is their earliest badge purchase.

    A buyer whose every badge is refunded or gone gets ``withdrawn_at`` rather
    than being deleted, so a check-in already recorded against them survives.
    """

    id = fields.IntField(pk=True)
    tenant: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.Tenant', related_name='check_in_entrants', on_delete=fields.CASCADE,
    )
    tenant_id: int
    event: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.CheckInEvent', related_name='entrants', on_delete=fields.CASCADE,
    )
    event_id: int
    source = fields.CharEnumField(CheckInEntrantSource, max_length=16)
    matcherino_user_id = fields.CharField(max_length=64, null=True)
    display_name = fields.CharField(max_length=255)
    avatar_url = fields.CharField(max_length=512, null=True)
    auth_provider = fields.CharField(max_length=32, null=True)
    auth_id = fields.CharField(max_length=128, null=True)
    registered_at = fields.DatetimeField(null=True)
    # mypy cannot infer a JSONField's type parameter, as with every sibling.
    source_data = fields.JSONField(null=True)  # type: ignore[var-annotated]
    user: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        'models.User', related_name='check_in_entries', null=True, on_delete=fields.SET_NULL
    )
    user_id: Optional[int]
    link_method = fields.CharEnumField(CheckInLinkMethod, max_length=24, null=True)
    linked_by: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        'models.User', related_name='check_in_links_made', null=True, on_delete=fields.SET_NULL
    )
    withdrawn_at = fields.DatetimeField(null=True)
    checked_in_at = fields.DatetimeField(null=True)
    checked_in_by: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        'models.User', related_name='check_ins_performed', null=True, on_delete=fields.SET_NULL
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    passes: fields.ReverseRelation["CheckInPass"]

    class Meta:
        table = 'checkinentrant'
        unique_together = (('event', 'matcherino_user_id'), ('event', 'user'))
        indexes = (('event', 'checked_in_at'),)


class CheckInTier(Model):
    """A kind of badge sold on the event's Matcherino venue (Base, VIP, Day Pass).

    Mirrors a Matcherino *pass*. ``amount_cents`` orders tiers, and an entrant
    holding several badges shows under the most expensive one they still hold.
    A tier Matcherino stops listing is kept: badges already sold still point
    at it.
    """

    id = fields.IntField(pk=True)
    tenant: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.Tenant', related_name='check_in_tiers', on_delete=fields.CASCADE,
    )
    tenant_id: int
    event: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.CheckInEvent', related_name='tiers', on_delete=fields.CASCADE,
    )
    event_id: int
    matcherino_pass_id = fields.IntField()
    title = fields.CharField(max_length=255)
    amount_cents = fields.IntField(default=0)
    role = fields.CharField(max_length=32, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    passes: fields.ReverseRelation["CheckInPass"]

    class Meta:
        table = 'checkintier'
        unique_together = (('event', 'matcherino_pass_id'),)


class CheckInPass(Model):
    """One badge bought on the event's Matcherino venue.

    One row per purchase, not per person: a buyer can hold several badges (one
    of them often for a friend, whom the venue doesn't name), and ``code`` is
    what that friend shows at the door. ``entrant`` is the buyer's roster row.

    ``refunded_at`` is Matcherino's refund; ``removed_at`` marks a purchase
    that dropped out of the feed, kept rather than deleted for the same reason
    an entrant is withdrawn rather than deleted. ``source_data`` holds the
    purchase as served, minus the buyer's contact details and the payment
    ledger, which check-in has no use for.
    """

    id = fields.IntField(pk=True)
    tenant: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.Tenant', related_name='check_in_passes', on_delete=fields.CASCADE,
    )
    tenant_id: int
    event: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.CheckInEvent', related_name='passes', on_delete=fields.CASCADE,
    )
    event_id: int
    tier: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.CheckInTier', related_name='passes', on_delete=fields.CASCADE,
    )
    tier_id: int
    entrant: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        'models.CheckInEntrant', related_name='passes', null=True, on_delete=fields.SET_NULL,
    )
    entrant_id: Optional[int]
    matcherino_purchase_id = fields.IntField()
    buyer_matcherino_user_id = fields.CharField(max_length=64)
    code = fields.CharField(max_length=32)
    purchased_at = fields.DatetimeField(null=True)
    refunded_at = fields.DatetimeField(null=True)
    removed_at = fields.DatetimeField(null=True)
    # mypy cannot infer a JSONField's type parameter, as with every sibling.
    source_data = fields.JSONField(null=True)  # type: ignore[var-annotated]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'checkinpass'
        unique_together = (('event', 'matcherino_purchase_id'),)
        indexes = (('event', 'code'),)
