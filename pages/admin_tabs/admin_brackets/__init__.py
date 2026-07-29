"""Admin Brackets package — the staff surface for native tournament brackets.

Split from a single module once the stage form, manage and results dialogs each
grew a lifecycle's worth of rules: ``page`` owns the selector, table and row
dispatch, and hands each dialog the service, tenant and refresh callback it needs.
"""

from .page import admin_brackets_page

__all__ = ['admin_brackets_page']
