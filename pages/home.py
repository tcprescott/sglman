from nicegui import app, ui
from theme.base import BaseLayout
from pages.admin import admin_dashboard_page

def create() -> None:
    @ui.page('/')
    async def home():
        BaseLayout()

