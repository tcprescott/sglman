"""Mock flags and offline stand-ins for the third-party clients.

These ship in the application package rather than in ``tests/`` on purpose: the
``MOCK_*`` environment flags are a supported **development** mode (see
docs/features/discord.md#mock-mode), so services import ``is_mock_*()`` and select a
stub at runtime. Production safety comes from ``environment.py``, which refuses
to start when a mock flag is set while ``ENVIRONMENT=production``.
"""
