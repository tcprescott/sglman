"""Discord CDN avatar URLs derived from the hash we persist on ``User``.

We store the avatar *hash* (``User.discord_avatar``) rather than a URL, and
build the CDN path on demand. The hash is what Discord's own API returns, it
never expires on its own, and deriving the URL means a size or format change is
one edit here instead of a data migration.

Nothing is proxied or re-hosted: the browser fetches straight from
``cdn.discordapp.com``. A hash that has gone stale (the person changed their
avatar and we haven't seen them since) 404s, so every surface that renders one
keeps its non-avatar placeholder as the fallback.
"""

from __future__ import annotations

from typing import Optional, Protocol

CDN_BASE = 'https://cdn.discordapp.com'

# Discord serves powers of two from 16 to 4096; anything else is rejected.
DEFAULT_SIZE = 64


class _HasDiscordIdentity(Protocol):
    discord_id: Optional[int]
    discord_avatar: Optional[str]


def avatar_url(
    discord_id: Optional[int],
    avatar_hash: Optional[str],
    size: int = DEFAULT_SIZE,
) -> Optional[str]:
    """CDN URL for one avatar, or ``None`` when we have nothing to point at.

    Animated avatars (hashes prefixed ``a_``) are served as GIF; everything else
    as PNG.
    """
    if not discord_id or not avatar_hash:
        return None
    ext = 'gif' if avatar_hash.startswith('a_') else 'png'
    return f'{CDN_BASE}/avatars/{discord_id}/{avatar_hash}.{ext}?size={size}'


def user_avatar_url(
    user: Optional[_HasDiscordIdentity], size: int = DEFAULT_SIZE
) -> Optional[str]:
    """:func:`avatar_url` for a ``User`` row (``None`` for placeholders)."""
    if user is None:
        return None
    return avatar_url(user.discord_id, user.discord_avatar, size)
