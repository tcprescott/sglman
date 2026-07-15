from tortoise import fields
from tortoise.models import Model


class FeatureFlagGroup(Model):
    """A named, super-admin-defined bundle of feature flags — a live tier/plan.

    Global (platform-managed, no tenant FK), like ``RacetimeBot``. A tenant is
    assigned to at most one group (``Tenant.feature_group``) and its available
    features are derived from that group **live** — editing the group updates
    every tenant on it. A tenant with no group falls back to the single
    ``is_default`` group. ``flags`` is a list of :class:`~models.enums.FeatureFlag`
    values; unknown/legacy keys are ignored by the service, so retiring a flag
    never orphans a group. At most one group is ``is_default`` (enforced in the
    service, not the DB).
    """

    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100, unique=True)
    description = fields.TextField(null=True)
    flags = fields.JSONField(default=list)
    is_default = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'featureflaggroup'


class TenantFeatureFlag(Model):
    """Per-tenant **override** of one feature flag, on top of the tenant's group.

    Availability normally derives live from the tenant's ``FeatureFlagGroup`` (or
    the default group when ungrouped). This row is an explicit exception a
    super-admin sets for one tenant, plus the community's own enable toggle. Both
    columns are **tri-state**:

    * ``available``: NULL = inherit from the group; True/False = force on/off.
    * ``enabled``:   NULL = default (on whenever available); True/False = the
      community STAFF's sticky choice.

    A row with both columns NULL carries no information and is deleted. Effective
    state is computed in ``FeatureFlagService`` (override wins over group, group
    over default) — never read these columns raw.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField(
        'models.Tenant', related_name='feature_flags', on_delete=fields.CASCADE
    )
    flag = fields.CharField(max_length=64)
    # Tri-state: NULL = inherit from the group; True/False = explicit override.
    available = fields.BooleanField(null=True)
    # Tri-state: NULL = default (on when available); True/False = community choice.
    enabled = fields.BooleanField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'tenantfeatureflag'
        unique_together = (('tenant', 'flag'),)
        indexes = (('tenant',),)
