"""Shared SSRF guard for server-side outbound requests.

Before the app dereferences a URL that a user supplied — staff-managed webhook
targets, browser-supplied web-push endpoints — the destination host is resolved
and rejected when it points at a non-public address. This keeps an attacker from
aiming an outbound request at internal services, loopback, or the cloud metadata
endpoint (169.254.169.254).
"""

import asyncio
import ipaddress
import socket


async def ensure_public_host(hostname: str, *, subject: str = 'URL') -> None:
    """Raise ``ValueError`` unless every address ``hostname`` resolves to is public.

    Rejects private, loopback, link-local, reserved, multicast, and unspecified
    ranges — covering RFC1918, ``127.0.0.0/8``, ``169.254.0.0/16`` (incl. the
    ``169.254.169.254`` metadata endpoint), ``::1``, ``fc00::/7``, and friends.

    ``subject`` is woven into the error message (e.g. "Webhook URL", "Push
    subscription endpoint") so callers surface a domain-appropriate message.
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve {subject} host '{hostname}'") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"{subject} must point to a public address")
