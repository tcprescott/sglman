"""Dev-seed fixtures for one tenant's outbound + telemetry surfaces.

Split out of ``seed_dev.py`` when that module crossed the 800-line budget,
following the ``seed_brackets_for_tenant`` / ``seed_challonge_for_tenant``
convention already used there: one module per domain, called from inside the
caller's ``tenant_scope``. Idempotent (``get_or_create`` / existence-guarded)
and tenant-stamped like every other seeded row.

The audit-log fixtures deliberately stayed behind in ``seed_dev.py``: they
reference half a dozen other seeded rows (a proctor, an equipment card, a
tournament), and threading all of those through here would cost more clarity
than the split buys.
"""

import json

from models import Match, TelemetryEvent, Tenant, User, Webhook, WebhookDelivery


async def seed_observability_for_tenant(
    tenant: Tenant, staff: User, finished_match: Match, now_utc,
) -> None:
    """Seed the inactive dev webhook (plus one delivery row) and telemetry rows."""
    # --- Webhooks ---------------------------------------------------------
    # Inactive so a dev session never attempts outbound deliveries; the one
    # seeded delivery row makes the admin delivery log render regardless.
    webhook, _ = await Webhook.get_or_create(
        name="Dev Webhook (inactive)", tenant=tenant,
        defaults={
            "url": "http://127.0.0.1:9/dev-webhook",
            "secret": "dev-webhook-secret-not-real",
            "event_types": ["*"],
            "is_active": False,
        },
    )
    if not await WebhookDelivery.filter(webhook=webhook, tenant=tenant).exists():
        await WebhookDelivery.create(
            tenant=tenant, webhook=webhook, event_type="match.created",
            payload=json.dumps({"match_id": finished_match.id}, sort_keys=True),
            response_status=200, attempt_count=1, success=True,
            delivered_at=now_utc,
        )
    print(f"    [{tenant.slug}] webhooks ok")

    # --- Telemetry -------------------------------------------------------
    # One row per category (page / interaction / domain) so the admin
    # telemetry report renders each section.
    telemetry_specs = [
        ("page", "page.view", f"/t/{tenant.slug}/", "sess-dev-1"),
        ("interaction", "report.exported", f"/t/{tenant.slug}/admin", "sess-dev-1"),
        ("domain", "match.created", None, None),
    ]
    if await TelemetryEvent.filter(tenant=tenant).count() == 0:
        for category, event_type, path, session_id in telemetry_specs:
            await TelemetryEvent.create(
                tenant=tenant, user=staff, category=category,
                event_type=event_type, path=path, session_id=session_id,
                details=json.dumps({"seed": True}),
            )
    print(f"    [{tenant.slug}] telemetry ok")
