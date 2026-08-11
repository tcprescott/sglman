"""Admin Async Qualifiers package — the staff surface for self-paced qualifiers.

Split from a single module once the per-tab loaders arrived: ``page`` owns the
state, the loaders and the views, and ``shared`` holds the pure helpers, the tab
names and the column and slot definitions both the desktop table and the mobile
card read.
"""

from .page import admin_qualifiers_page

__all__ = ['admin_qualifiers_page']
