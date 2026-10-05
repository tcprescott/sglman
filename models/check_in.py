from tortoise import fields
from tortoise.models import Model

from .enums import CheckInEntrantSource, CheckInEventStatus, CheckInLinkMethod


class CheckInEvent(Model):
    """An in-person event whose attendees are checked in at a desk.

    Registration happens on Matcherino: ``matcherino_bounty_id`` names the
    bounty whose participant list is mirrored into :class:`CheckInEntrant`
    rows. It is nullable so an event can run on walk-ups alone. The sync
    bookkeeping (``last_synced_at``/``last_sync_error``/``last_sync_count``)
    is shown at the desk because the Matcherino endpoint is unofficial: when
    it breaks, the volunteers need to see that the roster is stale.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='check_in_events', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    matcherino_bounty_id = fields.IntField(null=True)
    status = fields.CharEnumField(CheckInEventStatus, default=CheckInEventStatus.DRAFT, max_length=16)
    sync_interval_minutes = fields.IntField(default=5)
    last_synced_at = fields.DatetimeField(null=True)
    last_sync_error = fields.TextField(null=True)
    last_sync_count = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    entrants: fields.ReverseRelation["CheckInEntrant"]

    class Meta:
        table = 'checkinevent'
        unique_together = (('tenant', 'matcherino_bounty_id'),)


class CheckInEntrant(Model):
    """One person on a check-in event's roster.

    A ``MATCHERINO`` row mirrors a bounty participant, keyed by
    ``matcherino_user_id``; a ``WALK_UP`` row was added by staff at the desk.
    ``user`` is the matched Wizzrobe account, which is a nice-to-have rather
    than a requirement — plenty of registrants have none.

    ``source_data`` is the participant object exactly as Matcherino last served
    it. Nothing reads it today; it is kept so a field Matcherino starts serving
    later (registration tiers are the expected one) can be backfilled from rows
    already synced instead of waiting on a fresh sync.

    A registrant who leaves the bounty gets ``withdrawn_at`` rather than being
    deleted, so a check-in already recorded against them survives.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='check_in_entrants', on_delete=fields.CASCADE)
    event = fields.ForeignKeyField('models.CheckInEvent', related_name='entrants', on_delete=fields.CASCADE)
    source = fields.CharEnumField(CheckInEntrantSource, max_length=16)
    matcherino_user_id = fields.CharField(max_length=64, null=True)
    display_name = fields.CharField(max_length=255)
    avatar_url = fields.CharField(max_length=512, null=True)
    auth_provider = fields.CharField(max_length=32, null=True)
    auth_id = fields.CharField(max_length=128, null=True)
    twitch_login = fields.CharField(max_length=255, null=True)
    registered_at = fields.DatetimeField(null=True)
    source_data = fields.JSONField(null=True)
    user = fields.ForeignKeyField(
        'models.User', related_name='check_in_entries', null=True, on_delete=fields.SET_NULL
    )
    link_method = fields.CharEnumField(CheckInLinkMethod, max_length=24, null=True)
    linked_by = fields.ForeignKeyField(
        'models.User', related_name='check_in_links_made', null=True, on_delete=fields.SET_NULL
    )
    withdrawn_at = fields.DatetimeField(null=True)
    checked_in_at = fields.DatetimeField(null=True)
    checked_in_by = fields.ForeignKeyField(
        'models.User', related_name='check_ins_performed', null=True, on_delete=fields.SET_NULL
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'checkinentrant'
        unique_together = (('event', 'matcherino_user_id'), ('event', 'user'))
        indexes = (('event', 'checked_in_at'),)
