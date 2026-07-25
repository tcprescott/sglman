"""REST API tests — one module per router family under ``api/routers/``.

These drive the FastAPI app in-process via ``httpx`` + ``ASGITransport`` (see
``tests/api_helpers.py``) against the shared in-memory SQLite fixture. The live
stack — middleware ordering, rate limiting, token→tenant resolution — is
exercised separately by the ``/api-validation`` skill, not from here.
"""
