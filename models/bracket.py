"""Native tournament bracket models (see docs/brackets-plan.md).

Wizzrobe manages brackets natively — generating, progressing, and standing
tournaments — instead of mirroring them from the Challonge API. The four models
here are all tenant-scoped:

* :class:`Bracket` — one *stage* of a tournament (a single-stage tournament has
  one row; a group→playoff tournament has several, ordered by ``stage_order``).
* :class:`BracketEntrant` — the tournament-level roster row that carries an
  entrant's identity across every stage (placeholder-friendly: a ``display_name``
  now, a linked ``user`` later).
* :class:`BracketEntry` — an entrant's participation within one stage (its seed,
  group, and — once the stage completes — ``final_rank``).
* :class:`BracketMatch` — one slot in a stage's persisted match graph, carrying
  the ``winner_to`` / ``loser_to`` progression pointers so elimination
  advancement is plain pointer-following once the graph is generated, and a
  nullable ``match`` FK — the same scheduling seam ``ChallongeMatch.match`` uses.

The pairing/progression engine is invoked only at generation (``start``) and at
per-round pairing (Swiss / round robin); at all other times these rows are the
source of truth.
"""

from tortoise import fields
from tortoise.models import Model

from .enums import (
    BracketEntrantStatus,
    BracketEntryStatus,
    BracketFormat,
    BracketMatchState,
    BracketState,
)


class Bracket(Model):
    """One stage of a tournament's bracket."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='brackets', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='brackets', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=255)
    format = fields.CharEnumField(BracketFormat, max_length=32)
    state = fields.CharEnumField(BracketState, default=BracketState.DRAFT, max_length=16)
    # 0-based position in the stage chain; a single-stage tournament has one row
    # at 0. Unique per tournament (see Meta).
    stage_order = fields.IntField(default=0)
    # Schema-validated at the service boundary (never trusted raw): grand-final
    # reset toggle, Swiss round count, group count + points, tiebreaker order,
    # and — on non-first stages — the advancement rule from the prior stage.
    config = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    entries = fields.ReverseRelation["BracketEntry"]
    bracket_matches = fields.ReverseRelation["BracketMatch"]

    class Meta:
        table = 'bracket'
        # tournament is itself tenant-scoped, so (tournament, stage_order) is a
        # tenant-safe unique; it also serves the stage-ordered list query.
        unique_together = (('tournament', 'stage_order'),)
        indexes = (('tournament',),)


class BracketEntrant(Model):
    """Tournament-level roster row carrying identity across stages.

    Placeholder-friendly: seed with a ``display_name`` now and link a ``user``
    later — one link fixes the entrant in every stage. Team support later = the
    entrant pointing at a team instead of a user; this indirection is the
    future-proofing.
    """

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='bracket_entrants', on_delete=fields.CASCADE)
    tournament = fields.ForeignKeyField('models.Tournament', related_name='bracket_entrants', on_delete=fields.CASCADE)
    display_name = fields.CharField(max_length=255)
    # SET_NULL: deleting a user detaches (and re-placeholders) their entrants
    # rather than erasing bracket history.
    user = fields.ForeignKeyField(
        'models.User', related_name='bracket_entrants', null=True, on_delete=fields.SET_NULL
    )
    status = fields.CharEnumField(BracketEntrantStatus, default=BracketEntrantStatus.ACTIVE, max_length=16)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # related fields
    entries = fields.ReverseRelation["BracketEntry"]

    class Meta:
        table = 'bracketentrant'
        indexes = (('tournament',), ('user',))


class BracketEntry(Model):
    """An entrant's participation in one stage."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='bracket_entries', on_delete=fields.CASCADE)
    bracket = fields.ForeignKeyField('models.Bracket', related_name='entries', on_delete=fields.CASCADE)
    entrant = fields.ForeignKeyField('models.BracketEntrant', related_name='entries', on_delete=fields.CASCADE)
    # Per-stage seed (stage 2's seeds derive from stage 1's final ranks).
    seed = fields.IntField(null=True)
    # Group-stage formats only; "Group A" is derived display, not a stored name.
    group_number = fields.IntField(null=True)
    # Written when the stage completes, after tiebreakers — this is what the next
    # stage's advancement consumes.
    final_rank = fields.IntField(null=True)
    status = fields.CharEnumField(BracketEntryStatus, default=BracketEntryStatus.ACTIVE, max_length=16)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'bracketentry'
        # An entrant participates in a stage at most once.
        unique_together = (('bracket', 'entrant'),)
        indexes = (('bracket',),)


class BracketMatch(Model):
    """One slot in a bracket stage's persisted match graph."""

    id = fields.IntField(pk=True)
    tenant = fields.ForeignKeyField('models.Tenant', related_name='bracket_matches', on_delete=fields.CASCADE)
    bracket = fields.ForeignKeyField('models.Bracket', related_name='bracket_matches', on_delete=fields.CASCADE)
    # Negative round numbers denote the losers bracket (start.gg's convention).
    round = fields.IntField()
    position = fields.IntField()
    # Group-stage formats only.
    group_number = fields.IntField(null=True)
    # SET_NULL on the entry slots: pruning an entry (e.g. a dropped placeholder)
    # empties the slot rather than deleting the match.
    entry1 = fields.ForeignKeyField(
        'models.BracketEntry', related_name='matches_as_entry1', null=True, on_delete=fields.SET_NULL
    )
    entry2 = fields.ForeignKeyField(
        'models.BracketEntry', related_name='matches_as_entry2', null=True, on_delete=fields.SET_NULL
    )
    winner = fields.ForeignKeyField(
        'models.BracketEntry', related_name='matches_won', null=True, on_delete=fields.SET_NULL
    )
    state = fields.CharEnumField(BracketMatchState, default=BracketMatchState.PENDING, max_length=16)
    # Progression pointers into the same graph: where this match's winner/loser
    # flow. The ``*_slot`` (1 or 2) says which entry slot they fill. Self-FK,
    # SET_NULL so pruning a downstream match just detaches the pointer.
    winner_to = fields.ForeignKeyField(
        'models.BracketMatch', related_name='feeder_winners', null=True, on_delete=fields.SET_NULL
    )
    winner_to_slot = fields.IntField(null=True)
    loser_to = fields.ForeignKeyField(
        'models.BracketMatch', related_name='feeder_losers', null=True, on_delete=fields.SET_NULL
    )
    loser_to_slot = fields.IntField(null=True)
    # The scheduling seam: a native bracket match links to a real ``Match`` the
    # same way ``ChallongeMatch.match`` does. SET_NULL so deleting the scheduled
    # Match detaches it (the bracket slot survives). Null until scheduled.
    match = fields.ForeignKeyField(
        'models.Match', related_name='bracket_match', null=True, on_delete=fields.SET_NULL
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = 'bracketmatch'
        # A stage's graph is uniquely addressed by (round, position).
        unique_together = (('bracket', 'round', 'position'),)
        indexes = (('bracket',), ('match',))
