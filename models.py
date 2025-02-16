from tortoise import fields
from tortoise.models import Model

class Match(Model):
    id = fields.IntField(pk=True)
    event_slug = fields.CharField(max_length=255)
    

class TestModel(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    value = fields.IntField()
    somethingelse = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)