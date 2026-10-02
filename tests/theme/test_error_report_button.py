""""Report this error" is offered only to someone whose report the service takes.

``FeedbackService.submit`` refuses non-members, so a button that opens the
dialog for them is a dead end, and the drawer's Feedback item already applies
the same test (``BaseLayout.offers_feedback``).
"""

import types
from typing import ClassVar

import pytest
from nicegui import Client, ui
from starlette.requests import Request

from theme.base import BaseLayout
from theme.error_page import render_error_page


class _Storage:
    user: ClassVar[dict] = {'authenticated': True}
    browser: ClassVar[dict] = {}


@pytest.fixture
def signed_in(monkeypatch):
    fake_app = types.SimpleNamespace(storage=_Storage())
    for module in ('theme.base', 'theme.error_page', 'theme.notice'):
        monkeypatch.setattr(f'{module}.app', fake_app, raising=False)


def _layout(*, member: bool, feedback: bool) -> BaseLayout:
    layout = BaseLayout(user=types.SimpleNamespace(preferred_name='X'))
    layout._prepared = True
    layout._is_member = member
    layout._show_feedback = feedback
    return layout


def _report_button_visible(client) -> bool:
    buttons = [
        el for el in client.elements.values()
        if isinstance(el, ui.button) and el.text == 'Report this error'
    ]
    assert len(buttons) == 1
    return buttons[0].visible


@pytest.mark.parametrize('member, feedback, shown', [
    (True, True, True),
    (False, True, False),
    (True, False, False),
])
def test_only_a_member_with_feedback_live_is_offered_it(signed_in, member, feedback, shown):
    request = Request({
        'type': 'http', 'method': 'GET', 'path': '/x', 'headers': [],
        'query_string': b'', 'root_path': '',
    })
    with Client(ui.page(''), request=request) as client:
        render_error_page(
            status_code=500, headline='Something went wrong', message='m',
            error_id='abc', layout=_layout(member=member, feedback=feedback),
        )
    assert _report_button_visible(client) is shown


def test_the_layout_exposes_what_the_page_title_needs():
    layout = BaseLayout(wordmark='Default')
    assert layout.wordmark == 'Default'
    assert BaseLayout().wordmark == 'Wizzrobe'
    assert layout.is_member is False and layout.offers_feedback is False
