from tortoise import fields
from tortoise.models import Model


class Tenant(Model):
    """One independent tournament community hosted on the shared deployment.

    Logical multitenancy: a single database, shared tables, and this row as the
    discriminator every scoped model points at. Addressable path-based at
    ``/t/<slug>`` on the platform host; ``domain`` is reserved for optional
    host-based addressing (not yet resolved). ``discord_guild_id`` is the routing
    key the shared one-bot-many-guilds process uses to map a guild back to its
    tenant(s) — it is **not** unique, so several communities may share one Discord
    server and the bot fans out over every linked tenant. ``config`` holds
    per-tenant knobs that don't warrant columns.
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    # URL-safe path routing key: ``https://<platform>/t/<slug>/…``. Mutable
    # unique column — every join is by ``tenant.id``, so re-slugging is a
    # one-row UPDATE.
    slug = fields.CharField(max_length=64, unique=True, index=True)
    # Optional custom domain for host-based addressing. Nullable + unique (many
    # NULLs allowed in Postgres); host-mode resolution is deferred, the column
    # exists so attaching a domain later needs no schema change.
    domain = fields.CharField(max_length=255, null=True, unique=True, index=True)
    # Discord guild this tenant owns; the shared bot routes gateway events and
    # role sync by matching this. Nullable until a guild is linked.
    discord_guild_id = fields.BigIntField(null=True, index=True)
    is_active = fields.BooleanField(default=True)
    # Assigned feature-flag group (live tier). NULL → falls back to the default
    # group. SET NULL on group delete so removing a group never orphans a tenant.
    feature_group = fields.ForeignKeyField(
        'models.FeatureFlagGroup', related_name='tenants',
        on_delete=fields.SET_NULL, null=True,
    )
    config = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'tenant'


class TenantMembership(Model):
    """Ties a global :class:`User` to a :class:`Tenant` they belong to.

    Queried across tenants (never auto-scoped): membership is what the auth layer
    checks to decide whether an authenticated user may see a tenant at all.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='memberships', on_delete=fields.CASCADE)
    user = fields.ForeignKeyField('models.User', related_name='tenant_memberships', on_delete=fields.CASCADE)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'tenantmembership'
        unique_together = (('user', 'tenant'),)
        indexes = (('tenant',),)  # composite is user-first; per-tenant member enumeration uncovered
