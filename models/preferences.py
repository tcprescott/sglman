"""Per-user UI preferences that outlive a session.

``UserTablePreference`` is deliberately **global**, with no ``tenant`` FK. This is the ``User.timezone``
case: which columns a person wants on the Users board is a property of the
table, not of the community whose rows fill it, and someone who is staff in two
communities wants one answer rather than two. The practical consequence is that
there is no tenant column to scope, stamp, or leak-test.

``NavPreference`` is the opposite call: the side menu lists one community's
sections, so what someone pins in one community means nothing in another.
"""

from tortoise import fields
from tortoise.models import Model


class UserTablePreference(Model):
    """One person's saved layout for one table."""

    id = fields.IntField(pk=True)
    # The annotations below and the ignore on ``__str__`` are the Tortoise shape
    # mypy cannot see: a field descriptor's type and the ``<fk>_id`` shadow
    # column are both built at class-creation time. Every other model file
    # carries the same errors in the mypy baseline; a new file has to state them
    # at the line instead.
    user: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.User', related_name='table_preferences', on_delete=fields.CASCADE)
    # Stable identifier for one table, e.g. ``admin.users``. Declared as a
    # constant in ``theme/tables/preferences.py`` so the guardrail can prove
    # uniqueness; stored here as an opaque string.
    table_key = fields.CharField(max_length=64)
    # Shape validated by TablePreferenceService.validate; column *names* are
    # reconciled in presentation, never here.
    config: fields.Field = fields.JSONField(default=dict)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('user', 'table_key'),)

    def __str__(self) -> str:
        return f'{self.table_key} prefs for user {self.user_id}'  # type: ignore[attr-defined]


class NavPreference(Model):
    """One member's side menu in one community: pins and which sections are open.

    ``pins`` is an ordered list of tenant-local paths (``/home/my-schedule``,
    ``/admin/schedule``); the first four also fill the phone's bottom bar.
    ``None`` means "never edited", so the defaults apply, and is kept distinct
    from ``[]``, someone who unpinned everything. ``open_sections`` holds the
    keys of the menu sections left expanded (``home``, ``admin``,
    ``admin:Operations``), ``None`` again meaning "never touched".
    """

    id = fields.IntField(pk=True)
    tenant: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.Tenant', related_name='nav_preferences', on_delete=fields.CASCADE)
    tenant_id: int
    user: fields.ForeignKeyRelation = fields.ForeignKeyField(
        'models.User', related_name='nav_preferences', on_delete=fields.CASCADE)
    user_id: int
    pins: fields.Field = fields.JSONField(null=True)
    open_sections: fields.Field = fields.JSONField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'nav_preference'
        unique_together = (('tenant', 'user'),)

    def __str__(self) -> str:
        return f'nav prefs for user {self.user_id} in tenant {self.tenant_id}'  # type: ignore[attr-defined]
