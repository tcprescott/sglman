"""Password sign-in at ``/password-login``: unlisted, for accounts a platform
admin gave a password.

Nothing links here. It works on the platform host, under ``/t/<slug>`` and on a
community's own domain, and signs the browser in on whichever host serves it.
Every failure reads the same, so the page never says whether a name exists.
"""

from typing import Optional

from nicegui import Client, app, ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from application.services import PasswordAuthService, TenantService
from application.services.password_auth_service import normalize_login_name
from application.utils import login_throttle
from application.utils.tenant_urls import return_path_for_login, strip_root_path
from pages._session import start_session
from theme.banner import banner
from theme.chrome import render_platform_chrome
from theme.page_header import page_title

_MISMATCH = "That sign-in name and password don't match. Check both and try again."
_BLOCKED = 'Too many tries. Wait a few minutes, then try again.'


def create() -> None:
    @ui.page('/password-login')
    async def password_login(request: Request, client: Client) -> Optional[RedirectResponse]:
        root_path = request.scope.get('root_path', '') or ''
        next_param = request.query_params.get('next')
        if app.storage.user.get('authenticated', False):
            return RedirectResponse(return_path_for_login(root_path, next_param, None))
        return_to = return_path_for_login(root_path, next_param, app.storage.user.get('referrer_path'))

        ui.page_title('Sign in')
        render_platform_chrome(await TenantService.current_community_name() or None)

        state = {'error': None}

        @ui.refreshable
        def error_slot() -> None:
            if state['error']:
                with banner(state['error'], tone='danger'):
                    pass

        async def submit() -> None:
            name = normalize_login_name(name_input.value)
            try:
                browser_id = app.storage.browser.get('id')
            except Exception:
                browser_id = None
            if login_throttle.is_blocked(name, browser_id):
                state['error'] = _BLOCKED
                error_slot.refresh()
                return
            button.props('loading')
            try:
                user = await PasswordAuthService().authenticate(name, password_input.value or '')
            finally:
                button.props(remove='loading')
            if user is None:
                login_throttle.record_failure(name, browser_id)
                state['error'] = _MISMATCH
                password_input.value = ''
                error_slot.refresh()
                return
            login_throttle.record_success(name)
            app.storage.user.clear()
            start_session(user, {'username': user.username, 'avatar': None}, password=True)
            # Tenant-local: this page is served under root_path and the client
            # prepends it, so a qualified path would double it.
            ui.navigate.to(strip_root_path(root_path, return_to))

        with ui.column().classes('password-login w-full items-center q-pa-md'):
            with ui.card().classes('password-login__card w-full gap-3').props('flat bordered'):
                page_title('Sign in')
                error_slot()
                name_input = ui.input('Sign-in name').props(
                    'outlined dense autocomplete=username autocapitalize=none spellcheck=false',
                ).classes('w-full')
                password_input = ui.input(
                    'Password', password=True, password_toggle_button=True,
                ).props('outlined dense autocomplete=current-password').classes('w-full')
                button = ui.button('Sign in', on_click=submit).props('color=primary unelevated').classes('w-full')
                name_input.on('keydown.enter', submit)
                password_input.on('keydown.enter', submit)
        return None
