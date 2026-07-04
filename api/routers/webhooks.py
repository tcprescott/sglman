"""Outbound webhook management endpoints (Staff only)."""

from typing import List

from fastapi import APIRouter, Depends, status

from api.dependencies import ServiceErrorRoute, require_staff, require_staff_write
from api.schemas.webhooks import (
    WebhookCreate,
    WebhookCreatedResponse,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookSecretResponse,
    WebhookUpdate,
)
from application.services import WebhookService
from models import User

router = APIRouter(prefix="/webhooks", tags=["Webhooks"], route_class=ServiceErrorRoute)


@router.get("", response_model=List[WebhookResponse], summary="List webhooks (Staff only)")
async def list_webhooks(actor: User = Depends(require_staff)):
    return await WebhookService().list_webhooks(actor)


@router.post(
    "",
    response_model=WebhookCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook (Staff only) — secret returned once",
)
async def create_webhook(body: WebhookCreate, actor: User = Depends(require_staff_write)):
    return await WebhookService().create_webhook(
        actor,
        name=body.name,
        url=body.url,
        event_types=body.event_types,
        is_active=body.is_active,
    )


@router.get("/{webhook_id}", response_model=WebhookResponse, summary="Get a webhook (Staff only)")
async def get_webhook(webhook_id: int, actor: User = Depends(require_staff)):
    return await WebhookService().get_webhook(actor, webhook_id)


@router.put("/{webhook_id}", response_model=WebhookResponse, summary="Update a webhook (Staff only)")
async def update_webhook(
    webhook_id: int, body: WebhookUpdate, actor: User = Depends(require_staff_write)
):
    return await WebhookService().update_webhook(
        actor,
        webhook_id,
        name=body.name,
        url=body.url,
        event_types=body.event_types,
        is_active=body.is_active,
    )


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook (Staff only)",
)
async def delete_webhook(webhook_id: int, actor: User = Depends(require_staff_write)):
    await WebhookService().delete_webhook(actor, webhook_id)


@router.post(
    "/{webhook_id}/regenerate-secret",
    response_model=WebhookSecretResponse,
    summary="Rotate a webhook's signing secret (Staff only) — returned once",
)
async def regenerate_secret(webhook_id: int, actor: User = Depends(require_staff_write)):
    secret = await WebhookService().regenerate_secret(actor, webhook_id)
    return WebhookSecretResponse(secret=secret)


@router.get(
    "/{webhook_id}/deliveries",
    response_model=List[WebhookDeliveryResponse],
    summary="List a webhook's recent delivery attempts (Staff only)",
)
async def list_deliveries(webhook_id: int, actor: User = Depends(require_staff)):
    return await WebhookService().list_deliveries(actor, webhook_id)
