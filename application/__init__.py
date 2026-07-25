"""Application layer — everything between the entry surfaces and the ORM.

Subpackages, in dependency order: :mod:`application.repositories` (pure data
access), :mod:`application.services` (business rules, audit, notifications),
:mod:`application.events` (the in-process event bus services publish to), and
:mod:`application.utils` (shared helpers and third-party clients). Modules at
this level are cross-cutting seams that no single service owns.
"""
