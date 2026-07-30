"""Web-push subscription rotation.

Unauthenticated by necessity, not by oversight: the only caller is the service
worker's ``pushsubscriptionchange`` handler, which wakes with no page, no
session and no user gesture, so there is no actor to present a bearer token.
The request authenticates itself instead by proving it holds the retired
subscription's ``auth`` secret — see ``WebPushService.rotate_subscription``.

Every other web-push operation is driven from the profile UI through
``WebPushService`` directly and needs no REST surface.
"""

from fastapi import APIRouter

from api.dependencies import ServiceErrorRoute
from api.schemas.web_push import WebPushRotateRequest, WebPushRotateResponse
from application.services import WebPushService

router = APIRouter(prefix='/web-push', tags=['Web Push'], route_class=ServiceErrorRoute)


@router.post(
    '/rotate',
    response_model=WebPushRotateResponse,
    summary='Re-point a device subscription its push service reissued',
)
async def rotate(body: WebPushRotateRequest) -> WebPushRotateResponse:
    await WebPushService().rotate_subscription(
        old_endpoint=body.old_endpoint,
        old_auth=body.old_auth,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
        user_agent=body.user_agent,
    )
    return WebPushRotateResponse(rotated=True)
