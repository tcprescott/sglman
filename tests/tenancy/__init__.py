"""Multitenancy tests — tenant context, request resolution, and leak tests.

``test_*isolation*.py`` modules are the leak tests the multitenancy contract
requires for every tenant-scoped model: write the same row under two tenants via
``tenant_scope`` and assert neither reads the other's. ``test_leak_test_coverage``
is the ratchet that keeps that set complete — it scans this package for the
model names, so a leak test must live here (or in a module matching
``*isolation*``) to count.
"""
