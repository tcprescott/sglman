from tortoise import fields
from tortoise.models import Model


class TenantFeatureFlag(Model):
    """Per-tenant state of one feature flag (two-tier, disabled by default).

    A flag is governed on two tiers: a super-admin grants ``available`` to a
    tenant on ``/platform``; that tenant's STAFF flip ``enabled`` for their
    community (Admin → Features). The feature is live only when
    ``available AND enabled``. A **missing row means both are False** — the
    disabled-by-default posture, so a new flag needs no per-tenant backfill to be
    off everywhere.

    ``flag`` stores a :class:`~models.enums.FeatureFlag` value. The service
    ignores unknown/legacy keys, so retiring a flag never orphans a read.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField(
        'models.Tenant', related_name='feature_flags', on_delete=fields.CASCADE
    )
    flag = fields.CharField(max_length=64)
    # Super-admin tier: is this feature offered to the tenant at all.
    available = fields.BooleanField(default=False)
    # Tenant tier: has the tenant switched it on (only meaningful when available).
    enabled = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'tenantfeatureflag'
        unique_together = (('tenant', 'flag'),)
        indexes = (('tenant',),)
