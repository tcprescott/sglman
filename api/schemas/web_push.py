"""Schemas for the web-push subscription-rotation endpoint."""

from typing import Optional

from pydantic import BaseModel, Field


class WebPushRotateRequest(BaseModel):
    """A ``pushsubscriptionchange`` rotation posted by the service worker."""

    old_endpoint: str = Field(
        ..., max_length=1024, description='Endpoint of the subscription the push service retired.'
    )
    old_auth: str = Field(
        ...,
        max_length=64,
        description=(
            'The retired subscription\'s RFC 8291 auth secret (base64url). '
            'Proves the caller owns the subscription being rotated.'
        ),
    )
    endpoint: str = Field(..., max_length=1024, description='Endpoint of the reissued subscription.')
    p256dh: str = Field(..., max_length=128, description='Reissued client public key (base64url).')
    auth: str = Field(..., max_length=64, description='Reissued auth secret (base64url).')
    user_agent: Optional[str] = Field(None, max_length=255)


class WebPushRotateResponse(BaseModel):
    rotated: bool
