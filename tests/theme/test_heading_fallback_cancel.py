"""A tab build cancelled mid-await must not raise over its own cancellation.

Sentry SGLMAN-11: the Tournaments tab was still loading when its page went
away. NiceGUI deleted every element, then cancelled the build; the hidden
fallback heading's cleanup tried to delete the label a second time and raised
``list.remove(x): x not in list``, which was logged as a failed tab build.
"""

import asyncio

import pytest

from theme import page_header


class _DeletedLabel:
    tag = 'span'
    is_deleted = True

    def classes(self, *_args, **_kwargs):
        return self

    def delete(self):
        raise ValueError('list.remove(x): x not in list')


def test_cancelled_build_keeps_its_cancellation(monkeypatch):
    monkeypatch.setattr(page_header.ui, 'label', lambda *_a, **_k: _DeletedLabel())
    with pytest.raises(asyncio.CancelledError):
        with page_header.heading_fallback('Tournaments'):
            page_header._titled.set(True)
            raise asyncio.CancelledError


def test_live_fallback_is_still_removed_when_the_tab_brings_a_title(monkeypatch):
    deleted = []

    class _Label(_DeletedLabel):
        is_deleted = False

        def delete(self):
            deleted.append(True)

    monkeypatch.setattr(page_header.ui, 'label', lambda *_a, **_k: _Label())
    with page_header.heading_fallback('Tournaments'):
        page_header._titled.set(True)
    assert deleted == [True]
