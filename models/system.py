from tortoise import fields
from tortoise.models import Model


class SystemConfiguration(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='system_configurations', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    value = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'systemconfiguration'
        unique_together = (('tenant', 'name'),)
