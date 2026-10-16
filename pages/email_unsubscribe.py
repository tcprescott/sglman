"""The "Stop these emails" link at the bottom of every notification email.

``GET`` shows a one-button confirmation (a mail scanner that prefetches links
must not unsubscribe anyone); ``POST`` turns email notifications off, and is
also the RFC 8058 one-click target named in the ``List-Unsubscribe-Post``
header. Signed out and outside any community, since stopping mail must always
work.
"""

import html

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from application.services import NotificationChannelService

PATH = '/notifications/email/unsubscribe'

_PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Email notifications</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;color:#1C1B19;background:#F5F5F4}}
button{{font:inherit;font-weight:700;padding:10px 18px;border-radius:8px;border:0;background:#9C6B12;color:#fff;cursor:pointer}}
@media (prefers-color-scheme:dark){{body{{color:#ECEBE8;background:#161513}}button{{background:#E0A82E;color:#1C1B19}}}}</style>
</head><body><h1 style="font-size:1.4rem">{title}</h1><p>{body}</p>{form}</body></html>'''


def _page(title: str, body: str, form: str = '', status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        _PAGE.format(title=html.escape(title), body=html.escape(body), form=form),
        status_code=status,
        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'},
    )


def create(fastapi_app: FastAPI) -> None:
    @fastapi_app.get(PATH, include_in_schema=False)
    async def confirm(t: str = '') -> HTMLResponse:
        form = (
            f'<form method="post" action="{PATH}?t={html.escape(t, quote=True)}">'
            '<button type="submit">Stop email notifications</button></form>'
        )
        return _page(
            'Stop email notifications?',
            "You'll still get Discord DMs and any other notifications you've turned on.",
            form,
        )

    @fastapi_app.post(PATH, include_in_schema=False)
    async def unsubscribe(request: Request, t: str = '') -> HTMLResponse:
        if await NotificationChannelService().unsubscribe_email(t):
            return _page(
                'Email notifications are off',
                'You can turn them back on any time from Profile → Notifications in Wizzrobe.',
            )
        return _page(
            "That link didn't work",
            'It may be from an older email. Turn email off from Profile → Notifications in Wizzrobe instead.',
            status=400,
        )
