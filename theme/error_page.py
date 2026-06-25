"""Themed renderer for 40x / 50x error pages.

Wraps error content in the standard ``BaseLayout`` chrome (header, drawer,
footer, phoenix palette, dark mode) so error pages match the rest of the app.

The renderer is **synchronous** on purpose: NiceGUI invokes the
``on_page_exception`` handler without awaiting it (see ``nicegui/page.py``
``create_500_error_page``), so the 50x page must be built without ``await``.
The only async work — loading the user to file a feedback report — happens lazily
in the "Report this error" button's click handler.
"""

import logging

from nicegui import app, background_tasks, ui

from models import FeedbackCategory, User
from theme.base import BaseLayout

logger = logging.getLogger(__name__)


def render_error_page(
    *,
    status_code: int,
    headline: str,
    message: str,
    error_id: str | None = None,
    traceback_text: str | None = None,
    user: User | None = None,
) -> None:
    """Render a themed error page into the current page context.

    Args:
        status_code: HTTP status to display prominently (e.g. 404, 500).
        headline: Short title under the status code.
        message: Friendly explanation shown to the user.
        error_id: Traceable reference shown for 50x errors; when set, logged-in
            users get a "Report this error" button that prefills feedback.
        traceback_text: Full traceback for the debug diagnosis page; omit in
            production so internals are never exposed.
        user: Logged-in user (when known), used for the header/footer.
    """
    ui.page_title(f'{status_code} — SGL On Site')

    # Never let layout chrome throw from inside an error handler.
    try:
        BaseLayout(user=user).render_chrome()
    except Exception:  # pragma: no cover - defensive
        logger.exception('Failed to render error-page chrome')

    with ui.column().classes('error-page-container'):
        with ui.card().classes('error-card'):
            ui.label(str(status_code)).classes('error-status')
            ui.label(headline).classes('error-headline')
            ui.label(message).classes('error-message')

            if error_id:
                _remember_error_id(error_id)
                with ui.row().classes('error-ref-row items-center'):
                    ui.icon('tag').props('size=sm')
                    ui.label('Error reference:').classes('error-ref-label')
                    ui.label(error_id).classes('error-ref-id')

            with ui.row().classes('error-actions gap-2'):
                ui.button(
                    'Back to home', icon='home',
                    on_click=lambda: ui.navigate.to('/'),
                ).props('color=primary')
                if error_id and _is_authenticated():
                    ui.button(
                        'Report this error', icon='feedback',
                        on_click=lambda: background_tasks.create(_open_error_report(error_id)),
                    ).props('flat')

            if traceback_text:
                ui.label('Diagnostic details (development only)').classes('error-trace-title')
                ui.code(traceback_text, language='python').classes('error-trace')


def _is_authenticated() -> bool:
    try:
        return bool(app.storage.user.get('authenticated', False))
    except Exception:
        return False


def _remember_error_id(error_id: str) -> None:
    try:
        app.storage.user['last_error_id'] = error_id
    except Exception:
        pass


async def _open_error_report(error_id: str) -> None:
    """Load the current user lazily and open the prefilled feedback dialog."""
    from application.services.auth_service import current_user_from_storage
    from theme.dialog import FeedbackDialog

    user = await current_user_from_storage()
    if user is None:
        ui.notify('Please log in to report this error.', color='warning')
        return
    initial_message = (
        f'Error reference: {error_id}\n\n'
        'What I was doing when this happened:\n'
    )
    await FeedbackDialog(
        user,
        initial_category=FeedbackCategory.BUG.value,
        initial_message=initial_message,
    ).open()
