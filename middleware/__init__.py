"""ASGI middleware and the route-protection decorator.

Holds only request-pipeline concerns: authentication
(:mod:`~middleware.auth`, which also exports ``protected_page``), tenant
resolution from ``/t/<slug>`` (:mod:`~middleware.tenant`), response headers, and
error handlers. NiceGUI pages live in ``pages/``, not here.
"""
