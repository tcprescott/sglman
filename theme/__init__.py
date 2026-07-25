"""Shared presentation components — the reusable half of the UI layer.

Page chrome and layout (:mod:`~theme.base`), the ``ui.table`` families and their
mobile card views (``tables/``), modal dialogs (``dialog/``), the bracket
renderer (``brackets/``), and the live-update bridge
(:mod:`~theme.realtime`) that subscribes to ``application.events.match_live`` on
behalf of each connected client. Same rules as ``pages/``: services only, no
ORM writes.
"""
