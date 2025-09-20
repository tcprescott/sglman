from nicegui import app, ui

def create() -> None:
    @ui.page('/')
    async def home():
        def logout() -> None:
            app.storage.user.clear()
            ui.navigate.to('/login')
        ui.label(f'Hello {app.storage.user.get("username", "Guest")}!').classes('text-2xl')
        ui.button(on_click=logout, icon='logout').props('outline round')
