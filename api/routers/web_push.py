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
    description=(
        "Swaps a stored web-push subscription over to the one the browser's push service "
        "reissued, so the same person keeps getting notifications on that device. The "
        "browser's service worker calls this on its own when the subscription changes, and "
        "the rotation is recorded in the audit log.\n\n"
        "Fails with 400 when the new endpoint isn't an https URL on a public host or the new "
        "keys are malformed. Answers 404 when no stored subscription matches both "
        "`old_endpoint` and `old_auth`."
        "\n\n**Who can call this:** Anyone; no token needed. The request proves itself by "
        "carrying the retired subscription's auth secret, which only the subscribed browser holds."
    ),
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
