"""OAuth 2.1 authorization server for the MCP surface.

Same origin as the resource server, which is the simple case: a client that
finds ``/.well-known/oauth-protected-resource`` is pointed back here, and
discovers ``/.well-known/oauth-authorization-server`` on the same host.

The routes come from the SDK's ``create_auth_routes`` — authorize, token,
register (RFC 7591), revoke, and the RFC 8414 metadata — so PKCE and the grant
mechanics are the SDK's well-tested implementation rather than ours. They are
appended to the *outer* app so they land at the origin root; mounted under the
FastMCP sub-app they would sit beneath ``/mcp`` where no client looks.
"""

import logging

from fastapi import FastAPI
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl

from application.utils.environment import get_base_url
from mcpserver.oauth.provider import WizzrobeOAuthProvider
from mcpserver.wellknown import SCOPES_SUPPORTED

logger = logging.getLogger(__name__)

_provider: WizzrobeOAuthProvider | None = None


def get_provider() -> WizzrobeOAuthProvider:
    global _provider
    if _provider is None:
        _provider = WizzrobeOAuthProvider()
    return _provider


def register_oauth_routes(app: FastAPI) -> None:
    """Append the authorization-server routes to the outer app."""
    base = get_base_url()
    routes = create_auth_routes(
        provider=get_provider(),
        issuer_url=AnyHttpUrl(base),
        service_documentation_url=AnyHttpUrl(f'{base}/api/docs'),
        # Registration is open because MCP clients self-configure from a URL;
        # see McpAuthService.register_client for why that grants nothing.
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=SCOPES_SUPPORTED,
            default_scopes=SCOPES_SUPPORTED,
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    app.router.routes.extend(routes)
    logger.info('MCP OAuth routes registered (issuer=%s)', base)
