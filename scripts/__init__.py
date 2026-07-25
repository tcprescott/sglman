"""Operational scripts — run directly (``poetry run python scripts/<name>.py``).

Not part of the running app. ``seed_dev.py`` is the exception that is also
imported: ``tests/test_seed_coverage.py`` executes it to assert every
tenant-scoped model gets at least one representative row.
"""
