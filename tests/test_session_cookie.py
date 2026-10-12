"""The login session cookie: how long it lasts and how it's flagged."""


def test_session_lasts_90_days_and_is_secure_in_production(monkeypatch):
    # frontend imports pages.auth, which builds a real Discord client at
    # import time unless mock mode is on.
    monkeypatch.setenv('MOCK_DISCORD', 'true')
    import frontend

    monkeypatch.setattr(frontend, 'is_production', lambda: True)
    kwargs = frontend._session_middleware_kwargs()
    assert kwargs['max_age'] == 90 * 24 * 60 * 60
    assert kwargs['https_only'] is True
    assert kwargs['same_site'] == 'lax'
