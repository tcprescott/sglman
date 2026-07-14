from tortoise import fields
from tortoise.models import Model

from .enums import DiscordEventSource


class DiscordScheduledEvent(Model):
    """A Discord Scheduled Event mirrored from an SGLMan schedule row (PR 8).

    Tenant-scoped reconciliation link. The reconciler keeps the tenant guild's
    Scheduled Events in sync with its schedule: ``content_hash`` drives
    update-vs-noop, and the working set is **only this tenant's own rows** —
    never every event in the guild — so a shared guild never has a sibling
    tenant's events cancelled (``discord_guild_id`` is not unique).

    Uniqueness: ``discord_event_id`` is globally unique (one link per Discord
    event); ``(tenant, source_type, source_id)`` is unique for idempotency (one
    mirrored event per source row).
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='discord_scheduled_events', on_delete=fields.CASCADE)
    # The guild the event lives in, snapshotted from ``Tenant.discord_guild_id``
    # at creation so a later re-link doesn't silently orphan the row.
    guild_id = fields.BigIntField()
    discord_event_id = fields.BigIntField(unique=True)
    source_type = fields.CharEnumField(DiscordEventSource, max_length=20)
    source_id = fields.IntField()
    title = fields.CharField(max_length=255)
    scheduled_at = fields.DatetimeField(null=True)
    content_hash = fields.CharField(max_length=64, null=True)
    synced_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'discordscheduledevent'
        unique_together = (('tenant', 'source_type', 'source_id'),)
        indexes = (('tenant',), ('guild_id',))
