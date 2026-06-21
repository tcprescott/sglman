"""HTTP security-header middleware.

Adds defense-in-depth response headers to every request. The set is chosen to
be safe for the NiceGUI frontend: anti-clickjacking, MIME-sniffing protection,
and a referrer policy always; HSTS only in production (where TLS terminates in
front of the app).

A full script/style ``Content-Security-Policy`` is intentionally *not* set here
because NiceGUI/Quasar rely on inline scripts and styles; only ``frame-ancestors``
is asserted, which blocks framing without affecting asset loading.
"""

from starlette.middleware.base import BaseHTTPMiddleware

from application.utils.environment import is_production

_STATIC_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "frame-ancestors 'none'",
    'Referrer-Policy': 'strict-origin-when-cross-origin',
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for header, value in _STATIC_HEADERS.items():
            response.headers.setdefault(header, value)
        if is_production():
            response.headers.setdefault(
                'Strict-Transport-Security',
                'max-age=31536000; includeSubDomains',
            )
        return response
