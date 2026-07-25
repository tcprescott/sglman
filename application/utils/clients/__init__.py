"""HTTP clients for the third-party services Wizzrobe talks to.

One module per provider — Challonge, racetime.gg, SpeedGaming, Twitch, and the
shared OAuth identity-link client. All are ``httpx.AsyncClient``-based (never
``requests``: a sync call would freeze the shared event loop). Each has a
counterpart in :mod:`application.utils.mocks` that the owning service swaps in
when the matching ``MOCK_*`` flag is set.
"""
