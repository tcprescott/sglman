from tortoise import fields
from tortoise.models import Model

class Match(Model):
    id = fields.IntField(pk=True)
    event_slug = fields.CharField(max_length=255)
    scheduled_start = fields.DatetimeField()
    state = fields.CharField(max_length=30)
    broadcast_channel = fields.ForeignKeyField('models.BroadcastChannel', related_name='channel')
    external_match_source = fields.CharField(max_length=255, null=True) # e.g. "speedgaming"
    external_match_id = fields.CharField(max_length=255, null=True) # e.g. "63624"
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    players: fields.ReverseRelation["MatchPlayers"]

class Player(Model):
    id = fields.IntField(pk=True)
    display_name = fields.CharField(max_length=255)
    discord_id = fields.CharField(max_length=255)
    external_player_source = fields.CharField(max_length=255, null=True) # e.g. "speedgaming"
    external_player_id = fields.CharField(max_length=255, null=True) # e.g. "63624"
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    matches: fields.ReverseRelation["MatchPlayers"]

class MatchPlayers(Model):
    id = fields.IntField(pk=True)
    match = fields.ForeignKeyField('models.Match', related_name='match')
    player = fields.ForeignKeyField('models.Player', related_name='players')
    team = fields.IntField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class BroadcastChannel(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    short_name = fields.CharField(max_length=255)
    twitch_channel = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

class TestModel(Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    value = fields.IntField()
    somethingelse = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)