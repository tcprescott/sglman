"""Drift guard between audited actions and webhook-deliverable events.

``EventType`` names mirror ``AuditActions`` verbatim (identical ``object.verb``
strings), so every audited state-change is a *candidate* webhook event. A new
audited action should therefore either gain a matching ``EventType`` (making it
deliverable to webhook subscribers) or be consciously recorded below as
intentionally event-less. This test fails when a new ``AuditAction`` is added
without that decision — turning "did we forget to emit an event?" into a red
test instead of a code-review catch. (This is exactly how ``match.stage_assigned``
sat audited-but-not-emitted for a while.)

To resolve a failure:
- add the mirror member to ``EventType`` + ``EventType.ALL`` to emit it, **or**
- add the action to ``_EVENT_CANDIDATES`` (plausible future event) or
  ``_EXCLUDED_BY_DESIGN`` (never webhook it) with the reasoning.
"""

from application.events import EventType
from application.services.audit_service import AuditActions


def _audit_action_values() -> set[str]:
    return {
        value
        for name, value in vars(AuditActions).items()
        if not name.startswith('_') and isinstance(value, str)
    }


# Audited today, plausibly worth emitting later, but no consumer needs it yet.
_EVENT_CANDIDATES = frozenset({
    AuditActions.MATCH_REQUESTED,
    AuditActions.TOURNAMENT_CREATED,
    AuditActions.TOURNAMENT_UPDATED,
    AuditActions.TOURNAMENT_DELETED,
    AuditActions.STREAM_ROOM_CREATED,
    AuditActions.STREAM_ROOM_UPDATED,
    AuditActions.STREAM_ROOM_DELETED,
    AuditActions.TRIFORCE_TEXT_SUBMITTED,
    AuditActions.TRIFORCE_TEXT_APPROVED,
    AuditActions.TRIFORCE_TEXT_REJECTED,
    AuditActions.EQUIPMENT_CHECKED_OUT,
    AuditActions.EQUIPMENT_CHECKED_IN,
    AuditActions.VOLUNTEER_CHECKED_IN,
})

# Deliberately never webhooked: security-sensitive, internal plumbing, or noise.
_EXCLUDED_BY_DESIGN = frozenset({
    # Personal watch toggles — high volume, no domain interest.
    AuditActions.MATCH_WATCHER_ADDED,
    AuditActions.MATCH_WATCHER_REMOVED,
    # Permission/role administration.
    AuditActions.TOURNAMENT_ADMIN_GRANTED,
    AuditActions.TOURNAMENT_ADMIN_REVOKED,
    AuditActions.TOURNAMENT_CREW_COORDINATOR_GRANTED,
    AuditActions.TOURNAMENT_CREW_COORDINATOR_REVOKED,
    AuditActions.USER_ROLE_GRANTED,
    AuditActions.USER_ROLE_REVOKED,
    # Account / PII internals.
    AuditActions.USER_CREATED,
    AuditActions.USER_PROVISIONED,
    AuditActions.USER_PROFILE_UPDATED,
    AuditActions.USER_SELF_PROFILE_UPDATED,
    AuditActions.USER_ACTIVATION_CHANGED,
    AuditActions.USER_TOURNAMENT_ENROLLMENT_UPDATED,
    # Discord role mapping / sync plumbing.
    AuditActions.DISCORD_ROLE_MAPPING_ADDED,
    AuditActions.DISCORD_ROLE_MAPPING_REMOVED,
    AuditActions.ROLE_DISCORD_SYNC_GRANTED,
    AuditActions.ROLE_DISCORD_SYNC_REVOKED,
    AuditActions.ROLE_DISCORD_SYNC_BULK,
    # System configuration.
    AuditActions.SYSTEM_CONFIG_UPDATED,
    AuditActions.TRIFORCE_TEXT_DELETED,
    # Secrets — leaking these to arbitrary receivers is a risk.
    AuditActions.APITOKEN_CREATED,
    AuditActions.APITOKEN_REVOKED,
    # Webhook meta: a webhook about webhook config (incl. secret regen) is a footgun.
    AuditActions.WEBHOOK_CREATED,
    AuditActions.WEBHOOK_UPDATED,
    AuditActions.WEBHOOK_DELETED,
    AuditActions.WEBHOOK_SECRET_REGENERATED,
    # In-app feedback triage.
    AuditActions.FEEDBACK_SUBMITTED,
    AuditActions.FEEDBACK_REVIEWED,
    # Equipment catalog CRUD (checkout/checkin are candidates above).
    AuditActions.EQUIPMENT_CREATED,
    AuditActions.EQUIPMENT_UPDATED,
    AuditActions.EQUIPMENT_DELETED,
    # Player availability edits.
    AuditActions.PLAYER_AVAILABILITY_UPDATED,
    # Challonge integration side-effects (result_pushed mirrors match.result_recorded).
    AuditActions.CHALLONGE_CONNECTED,
    AuditActions.CHALLONGE_DISCONNECTED,
    AuditActions.CHALLONGE_PLAYER_LINKED,
    AuditActions.CHALLONGE_PLAYER_UNLINKED,
    AuditActions.CHALLONGE_PLAYER_USERNAME_UPDATED,
    AuditActions.CHALLONGE_TOURNAMENT_LINKED,
    AuditActions.CHALLONGE_BRACKET_SYNCED,
    AuditActions.CHALLONGE_RESULT_PUSHED,
    AuditActions.CHALLONGE_WEBHOOK_SYNCED,
    # Twitch account linking.
    AuditActions.TWITCH_LINKED,
    AuditActions.TWITCH_UNLINKED,
    # Volunteer opt-in state, scheduling config, and bulk draft churn.
    AuditActions.VOLUNTEER_OPTED_IN,
    AuditActions.VOLUNTEER_OPTED_OUT,
    AuditActions.VOLUNTEER_POSITION_CREATED,
    AuditActions.VOLUNTEER_POSITION_UPDATED,
    AuditActions.VOLUNTEER_POSITION_DELETED,
    AuditActions.VOLUNTEER_SHIFT_CREATED,
    AuditActions.VOLUNTEER_SHIFT_UPDATED,
    AuditActions.VOLUNTEER_SHIFT_DELETED,
    AuditActions.VOLUNTEER_AVAILABILITY_UPDATED,
    AuditActions.VOLUNTEER_DRAFT_GENERATED,
    AuditActions.VOLUNTEER_DRAFT_CLEARED,
    AuditActions.VOLUNTEER_SHIFTS_RESET,
    AuditActions.VOLUNTEER_QUALIFICATIONS_UPDATED,
    # Per-device push subscription state.
    AuditActions.WEB_PUSH_SUBSCRIBED,
    AuditActions.WEB_PUSH_UNSUBSCRIBED,
    # Tenant ↔ Discord-server connection: admin infrastructure configuration,
    # not a tournament domain event a webhook subscriber would act on.
    AuditActions.DISCORD_SERVER_LINKED,
    AuditActions.DISCORD_SERVER_UNLINKED,
    # Tenancy / platform administration: super-admin-only, platform-level
    # (tenant=NULL) rows. Webhooks are tenant-scoped, so a platform event would
    # reach zero subscribers — and tenant CRUD / role grants are sensitive.
    AuditActions.TENANT_CREATED,
    AuditActions.TENANT_UPDATED,
    AuditActions.TENANT_DELETED,
    AuditActions.TENANT_MEMBER_ADDED,
    AuditActions.TENANT_MEMBER_REMOVED,
    AuditActions.SUPER_ADMIN_GRANTED,
    AuditActions.SUPER_ADMIN_REVOKED,
})

_EVENTLESS_AUDIT_ACTIONS = _EVENT_CANDIDATES | _EXCLUDED_BY_DESIGN


def test_no_untriaged_audit_actions():
    """Every audited action is emitted OR explicitly recorded as event-less."""
    untriaged = _audit_action_values() - set(EventType.ALL) - _EVENTLESS_AUDIT_ACTIONS
    assert not untriaged, (
        "Audited actions with neither an EventType nor an eventless-ledger entry: "
        f"{sorted(untriaged)}. Emit them on the event bus (add to EventType), or "
        "add them to _EVENT_CANDIDATES / _EXCLUDED_BY_DESIGN with a rationale."
    )


def test_eventless_ledger_has_no_stale_entries():
    """The ledger can't list something that is now emitted or no longer audited."""
    audited = _audit_action_values()
    now_emitted = _EVENTLESS_AUDIT_ACTIONS & set(EventType.ALL)
    assert not now_emitted, (
        f"Ledger entries that are now emitted events: {sorted(now_emitted)}. "
        "Remove them from the eventless ledger."
    )
    unknown = _EVENTLESS_AUDIT_ACTIONS - audited
    assert not unknown, (
        f"Ledger entries that are no longer real audit actions: {sorted(unknown)}."
    )
