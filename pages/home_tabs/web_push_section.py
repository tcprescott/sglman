"""Device notification (Web Push) management UI for the player profile page.

Lets a user enable native push notifications on the current device and manage
the devices already subscribed. Subscribing must happen inside the click
gesture (Safari refuses permission prompts outside one), so the enable/disable
buttons run ``static/js/web-push.js`` client-side via ``js_handler`` and report
back through ``emitEvent``; the server side then persists via
:class:`WebPushService`. The section renders nothing when VAPID keys are not
configured.
"""

import json

from nicegui import ui

from application.services import WebPushService
from application.utils.timezone import format_eastern_date
from models import User


def _device_label(user_agent: str | None) -> str:
    ua = user_agent or ''
    if 'iPhone' in ua:
        device = 'iPhone'
    elif 'iPad' in ua:
        device = 'iPad'
    elif 'Android' in ua:
        device = 'Android'
    elif 'Macintosh' in ua:
        device = 'Mac'
    elif 'Windows' in ua:
        device = 'Windows'
    elif 'Linux' in ua:
        device = 'Linux'
    else:
        device = 'Unknown device'
    if 'Edg/' in ua or 'EdgiOS/' in ua:
        browser = 'Edge'
    elif 'Firefox/' in ua or 'FxiOS/' in ua:
        browser = 'Firefox'
    elif 'Chrome/' in ua or 'CriOS/' in ua:
        browser = 'Chrome'
    elif 'Safari/' in ua:
        browser = 'Safari'
    else:
        browser = ''
    return f'{device} · {browser}' if browser else device


async def render_web_push_section(user: User) -> None:
    service = WebPushService()
    if not service.is_configured():
        return

    ui.add_head_html('<script src="/static/js/web-push.js"></script>')

    @ui.refreshable
    async def device_list() -> None:
        subscriptions = await service.list_subscriptions(user)
        if not subscriptions:
            ui.label('No devices subscribed yet.').classes('text-muted')
            return
        with ui.column().classes('input-full-width'):
            for sub in subscriptions:
                with ui.row().classes('row-centered').style('justify-content: space-between; width: 100%;'):
                    with ui.column().classes('gap-0'):
                        ui.label(_device_label(sub.user_agent)).classes('text-weight-medium')
                        added = f'Added {format_eastern_date(sub.created_at)}'
                        if sub.last_used_at:
                            added += f' · Last notified {format_eastern_date(sub.last_used_at)}'
                        ui.label(added).classes('text-muted text-caption')
                    ui.button(icon='delete', on_click=lambda _, sid=sub.id: remove(sid)) \
                        .props('flat dense color=negative')

    async def remove(subscription_id: int) -> None:
        try:
            await service.remove_subscription(user, subscription_id)
            ui.notify('Device removed.', color='positive', icon='check_circle')
        except ValueError as e:
            ui.notify(str(e), color='warning')
        device_list.refresh()

    async def on_subscribed(e) -> None:
        args = e.args or {}
        error = args.get('error')
        if error == 'ios_needs_install':
            ui.notify(
                'On iPhone/iPad, first add SGL On Site to your Home Screen '
                '(Share → Add to Home Screen), then enable notifications from the installed app.',
                color='warning', multi_line=True,
            )
            return
        if error == 'permission_denied':
            ui.notify('Notifications are blocked for this site in your browser settings.', color='warning')
            return
        if error == 'permission_dismissed':
            ui.notify('Notification permission was not granted — click Enable again and choose Allow.', color='warning')
            return
        if error == 'unsupported':
            ui.notify('This browser does not support push notifications.', color='warning')
            return
        if error:
            ui.notify(f'Could not enable notifications: {error}', color='warning')
            return
        subscription = args.get('subscription') or {}
        keys = subscription.get('keys') or {}
        try:
            await service.subscribe(
                user,
                endpoint=subscription.get('endpoint') or '',
                p256dh=keys.get('p256dh') or '',
                auth=keys.get('auth') or '',
                user_agent=args.get('userAgent'),
            )
        except ValueError as err:
            ui.notify(str(err), color='warning')
            return
        ui.notify('Notifications enabled on this device.', color='positive', icon='notifications_active')
        device_list.refresh()

    async def on_unsubscribed(e) -> None:
        args = e.args or {}
        if args.get('error'):
            # The browser-side unsubscribe failed — the device would keep
            # receiving pushes, so a success toast here would be a lie.
            ui.notify(f"Could not disable notifications: {args['error']}", color='warning')
            return
        endpoint = args.get('endpoint')
        if not endpoint:
            ui.notify('This device was not subscribed.', color='info')
            return
        removed = await service.unsubscribe(user, endpoint)
        ui.notify('Notifications disabled on this device.', color='positive', icon='notifications_off')
        if removed:
            device_list.refresh()

    ui.on('sgl_web_push_subscribed', on_subscribed)
    ui.on('sgl_web_push_unsubscribed', on_unsubscribed)

    public_key = service.get_public_key()

    with ui.card().classes('card-full-width'):
        ui.label('Device Notifications').classes('section-title')
        ui.label(
            'Get match and crew notifications directly on this device — no Discord app '
            'needed. Works on iPhone/iPad (iOS 16.4+, added to the Home Screen), Android, '
            'and desktop browsers. Notifications mirror the Discord DMs you already receive.'
        ).classes('text-muted text-caption')
        with ui.row().classes('button-row'):
            ui.button('Enable on this device', icon='notifications_active').props('color=primary dense').on(
                'click',
                js_handler=(
                    'async () => {'
                    f'const result = await window.sglWebPush.subscribe({json.dumps(public_key)});'
                    "emitEvent('sgl_web_push_subscribed', result);"
                    '}'
                ),
            )
            ui.button('Disable on this device', icon='notifications_off').props('flat dense').on(
                'click',
                js_handler=(
                    'async () => {'
                    'const result = await window.sglWebPush.unsubscribe();'
                    "emitEvent('sgl_web_push_unsubscribed', result);"
                    '}'
                ),
            )
        await device_list()
