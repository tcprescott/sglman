"""Per-user UI preferences that outlive a session.

Deliberately **global**, with no ``tenant`` FK. This is the ``User.timezone``
case: which columns a person wants on the Users board is a property of the
table, not of the community whose rows fill it, and someone who is staff in two
communities wants one answer rather than two. The practical consequence is that
there is no tenant column to scope, stamp, or leak-test.
"""

from tortoise import fields
from tortoise.models import Model


class UserTablePreference(Model):
    """One person's saved layout for one table."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        'models.User', related_name='table_preferences', on_delete=fields.CASCADE)
    # Stable identifier for one table, e.g. ``admin.users``. Declared as a
    # constant in ``theme/tables/preferences.py`` so the guardrail can prove
    # uniqueness; stored here as an opaque string.
    table_key = fields.CharField(max_length=64)
    # Shape validated by TablePreferenceService.validate; column *names* are
    # reconciled in presentation, never here.
    config = fields.JSONField(default=dict)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        unique_together = (('user', 'table_key'),)

    def __str__(self) -> str:
        return f'{self.table_key} prefs for user {self.user_id}'
