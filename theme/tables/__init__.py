"""``ui.table`` components and their mobile card views.

Every table here pairs with a card grid — :func:`~theme.tables.mobile_grid.enable_mobile_grid`
for most, a bespoke ``item`` slot for the family tables (match, user, tournament).
The match table is split across ``match.py`` (view), ``match_slots.py`` (Vue
templates), ``match_grid.py``, and ``match_handlers.py``.

The equipment surfaces (``pages/equipment.py``, ``pages/home_tabs/equipment.py``,
``pages/admin_tabs/admin_equipment.py``) build their tables inline rather than
through a component here.
"""
