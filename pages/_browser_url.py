"""Read the address bar of a page that only does work once its socket connects.

The OAuth and sign-in callbacks read ``window.location.href`` rather than the
request URL, because in host mode the browser's host is the one the flow has to
answer to. That needs a live socket, and plenty of visitors never open one: a
crawler, an iOS link preview, Safari parking the tab during the Discord hop.
``Client.connected()`` also returns when NiceGUI deletes such a client, so a page
that carries on reads ``None`` (or times out) and then touches a user storage
NiceGUI has already pruned.
"""

import logging

from nicegui import Client, ui

__all__ = ['browser_url']

logger = logging.getLogger(__name__)


async def browser_url(client: Client) -> str | None:
    """Wait for the socket and return the browser's URL, or ``None`` if it went away.

    A ``None`` means there is nobody left to answer: the caller returns without
    touching ``app.storage.user`` or navigating.
    """
    await client.connected()
    if client.is_deleted:
        logger.info('Page client went away before its socket connected; stopping.')
        return None
    try:
        url = await ui.run_javascript('window.location.href')
    except TimeoutError:
        logger.info('Browser did not report its URL; stopping.')
        return None
    if not url or client.is_deleted:
        logger.info('Page client went away while reading its URL; stopping.')
        return None
    return url
