"""Add indexes on hot-path foreign-key and reverse-lookup columns.

Tortoise does not create indexes on ``ForeignKeyField`` columns in Postgres,
and a ``unique_together`` composite only serves lookups on its *leftmost*
column — so filtering a junction table by its second column (e.g. ``matchwatcher``
by ``match_id`` when the unique key is ``(user_id, match_id)``) falls back to a
sequential scan. This migration adds the single-column (and one composite)
indexes that the repositories actually query on tables that grow across events,
so those reverse-relation reads — and the parent-row delete cascades that must
scan these same FK columns — stop scanning the whole table.

Hand-written (like migrations 14 and 18) to keep the numbered chain contiguous
with the ``Meta.indexes`` declarations added to ``models.py`` for schema-snapshot
parity. Every statement is idempotent (``IF NOT EXISTS``).
"""

from tortoise import BaseDBAsyncClient


# (index_name, table, columns) — each justified by a repository query; see the
# per-index note. Columns already covered by an existing index or by a
# composite's leftmost prefix are intentionally omitted.
_INDEXES = [
    # match: tournament/room filters drive nearly every schedule + report query.
    ("idx_match_tournament_id", "match", "tournament_id"),
    ("idx_match_stream_room_id", "match", "stream_room_id"),
    # matchplayers: "matches for this player" (get_for_player) resolves the user
    # first (discord_id is unique) then needs matchplayers by user_id; the
    # unique key is (match_id, user_id) so user_id alone is uncovered.
    ("idx_matchplayers_user_id", "matchplayers", "user_id"),
    # matchwatcher: notification fan-out filters by match_id; unique key is
    # (user_id, match_id) so match_id alone is uncovered.
    ("idx_matchwatcher_match_id", "matchwatcher", "match_id"),
    # tournamentplayers: "tournaments for this user"; unique key is
    # (tournament_id, user_id) so user_id alone is uncovered.
    ("idx_tournamentplayers_user_id", "tournamentplayers", "user_id"),
    # tournamentnotificationpreference: subscriber fan-out filters by
    # tournament_id; unique key is (user_id, tournament_id) so it is uncovered.
    ("idx_tnp_tournament_id", "tournamentnotificationpreference", "tournament_id"),
    # equipmentloan: per-asset open-loan / history and per-user holdings.
    ("idx_equipmentloan_equipment_id", "equipmentloan", "equipment_id"),
    ("idx_equipmentloan_borrower_id", "equipmentloan", "borrower_id"),
    # challongematch: bracket row for a scheduled match (pushed on every confirm)
    # and the participant-side OR-join on the player home tab.
    ("idx_challongematch_match_id", "challongematch", "match_id"),
    ("idx_challongematch_participant1_id", "challongematch", "participant1_id"),
    ("idx_challongematch_participant2_id", "challongematch", "participant2_id"),
    # challongeparticipant: resolve participants for a linked user.
    ("idx_challongeparticipant_user_id", "challongeparticipant", "user_id"),
    # volunteerassignment: "my shifts" + overlap checks; unique key is
    # (shift_id, user_id) so user_id alone is uncovered.
    ("idx_volunteerassignment_user_id", "volunteerassignment", "user_id"),
    # volunteerqualification: "who can fill this position" (auto-scheduler);
    # unique key is (user_id, position_id) so position_id alone is uncovered.
    ("idx_volunteerqualification_position_id", "volunteerqualification", "position_id"),
    # volunteershift: shifts for one position within a time window.
    ("idx_volunteershift_position_id", "volunteershift", "position_id"),
    # availability windows: read + overlap-match by user.
    ("idx_volunteeravailability_user_id", "volunteeravailability", "user_id"),
    ("idx_playeravailability_user_id", "playeravailability", "user_id"),
    # userrole: enumerate everyone holding a role; unique key is (user_id, role)
    # so role alone is uncovered.
    ("idx_userrole_role", "userrole", "role"),
    # feedback: staff review page orders the whole table by created_at.
    ("idx_feedback_created_at", "feedback", "created_at"),
]

# Composite indexes (table, index_name, "col_a, col_b").
_COMPOSITE_INDEXES = [
    # triforcetext: list_by_tournament (+approved) uses the tournament_id prefix;
    # list_by_tournament_and_user / list_approved_by_user use the full key.
    ("idx_triforcetext_tournament_user", "triforcetext", '"tournament_id", "user_id"'),
]


async def upgrade(db: BaseDBAsyncClient) -> str:
    statements = [
        f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}");'
        for name, table, column in _INDEXES
    ]
    statements += [
        f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ({columns});'
        for name, table, columns in _COMPOSITE_INDEXES
    ]
    return "\n".join(statements)


async def downgrade(db: BaseDBAsyncClient) -> str:
    names = [name for name, _, _ in _INDEXES] + [name for name, _, _ in _COMPOSITE_INDEXES]
    return "\n".join(f'DROP INDEX IF EXISTS "{name}";' for name in names)
