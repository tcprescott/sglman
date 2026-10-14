"""Small pieces every settings pane shares."""

from nicegui import app, ui

from application.services import get_user_from_session
from models import User


async def current_actor() -> User:
    """The signed-in user, looked up at save time rather than at build time."""
    actor = await get_user_from_session(app.storage.user)
    if actor is None:
        raise ValueError('Sign in again to save these settings.')
    return actor


def field_hint(text: str) -> ui.label:
    """The one-line explanation under a field."""
    return ui.label(text).classes('wiz-field-hint')


def positive_int_or_blank(value, what: str) -> str:
    """The stored form of an optional whole number of at least 1."""
    if value is None or value == '':
        return ''
    number = int(value)
    if number < 1:
        raise ValueError(f'{what} must be at least 1.')
    return str(number)
