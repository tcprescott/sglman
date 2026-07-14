from tortoise import fields
from tortoise.models import Model


class Webhook(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='webhooks', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    url = fields.CharField(max_length=1024)
    # Plaintext because it must be reproducible to sign each delivery (unlike a
    # hashed API token). Never returned by list/GET or written to logs.
    secret = fields.CharField(max_length=128)
    # List of EventType values this webhook fires on; ['*'] means every event.
    event_types = fields.JSONField(default=list)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'webhook'


class WebhookDelivery(Model):
    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='webhook_deliveries', on_delete=fields.CASCADE)
    webhook = fields.ForeignKeyField(
        'models.Webhook', related_name='deliveries', on_delete=fields.CASCADE
    )
    event_type = fields.CharField(max_length=100)
    payload = fields.TextField()
    response_status = fields.IntField(null=True)
    attempt_count = fields.IntField(default=0)
    success = fields.BooleanField(default=False)
    error = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)
    delivered_at = fields.DatetimeField(null=True)

    class Meta:
        table = 'webhookdelivery'
        indexes = (('webhook',),)
