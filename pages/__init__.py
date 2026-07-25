"""Presentation layer — the NiceGUI pages, registered by ``frontend.py``.

One module per route; the ``*_tabs/`` subpackages hold the tab bodies for the
multi-tab pages (``admin``, ``home``, ``volunteer``). Pages call services,
catch their ``ValueError``/``PermissionError`` and surface them with
``ui.notify()`` — no business logic and no ORM writes.
"""
