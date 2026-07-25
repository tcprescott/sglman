"""Shared helpers — the pieces no single service owns.

Top level holds the pure/cross-cutting helpers (timezone conversion,
environment validation, CSV export, hashing, QR codes, web push, Sentry, host
and tenant URL/session helpers, the background-loop runner). The two
subpackages hold the outward-facing halves: :mod:`~application.utils.clients`
for third-party HTTP clients and :mod:`~application.utils.mocks` for the
``MOCK_*`` flags and their offline stand-ins.

A peer of ``services/`` and ``repositories/``, so it is importable from any
layer — nothing here may import NiceGUI or reach into the ORM.
"""
