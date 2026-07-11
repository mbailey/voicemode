"""Middleware for VoiceMode HTTP/SSE server.

This module provides middleware to restrict access to the VoiceMode server:

1. IPAllowlistMiddleware - Restrict access based on client IP addresses.
   Supports CIDR notation for flexible IP range configuration. The allowlist
   is checked against the direct TCP peer; X-Forwarded-For is only honored
   when the peer is a configured trusted proxy (GHSA-2qvv-vjq9-g5r4).

2. TokenAuthMiddleware - Bearer token authentication via Authorization header.
   Validates Bearer tokens for API-style authentication.

Usage:
    from voice_mode.serve_middleware import (
        IPAllowlistMiddleware,
        TokenAuthMiddleware,
        ANTHROPIC_CIDRS,
        LOCAL_CIDRS,
    )

    # Allow localhost + Anthropic IPs
    allowed = LOCAL_CIDRS + ANTHROPIC_CIDRS
    app.add_middleware(IPAllowlistMiddleware, allowed_cidrs=allowed)

    # Require Bearer token authentication
    app.add_middleware(TokenAuthMiddleware, token="my-secret-token")
"""

import ipaddress
import logging
import time
from typing import Callable, List, Optional, Union

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("voicemode")


# Anthropic's outbound IP ranges for Claude Code connections
# See: https://docs.anthropic.com/en/docs/resources/ip-addresses
ANTHROPIC_CIDRS: List[str] = [
    "160.79.104.0/21",  # Primary outbound range
    # Legacy individual IPs (as /32 CIDRs)
    "35.193.26.195/32",
    "35.202.227.108/32",
    "35.224.6.40/32",
    "35.224.118.189/32",
]

# Tailscale CGNAT range - covers all devices on any tailnet
# These IPs are only routable within your tailnet (private network)
TAILSCALE_CIDRS: List[str] = [
    "100.64.0.0/10",  # Tailscale CGNAT range
]

# Local and private network ranges
LOCAL_CIDRS: List[str] = [
    "127.0.0.0/8",      # IPv4 localhost
    "10.0.0.0/8",       # Private Class A
    "172.16.0.0/12",    # Private Class B
    "192.168.0.0/16",   # Private Class C
    "::1/128",          # IPv6 localhost
]


def get_client_ip(
    request: Request, trusted_proxies: Optional[List[str]] = None
) -> str:
    """Extract the real client IP address from a request.

    Security (GHSA-2qvv-vjq9-g5r4): the ``X-Forwarded-For`` header is
    attacker-controllable, so it is only honored when the *direct TCP peer*
    is itself a configured trusted proxy. When ``trusted_proxies`` is empty
    or the direct peer is not within it, the header is ignored entirely and
    the direct peer address is returned. This prevents an unauthenticated
    attacker from spoofing an allowed IP to bypass the IP allowlist.

    When the direct peer *is* a trusted proxy, the forwarded chain is walked
    from right to left, skipping any hops that are themselves trusted
    proxies, and the first untrusted address is returned as the real client.
    If the whole chain is trusted (or the header is absent/empty), the direct
    peer is returned.

    Args:
        request: The Starlette request object.
        trusted_proxies: CIDR ranges whose members are trusted to set
            ``X-Forwarded-For``. Defaults to none (header never trusted).

    Returns:
        The client IP address as a string.
    """
    direct_peer = request.client.host if request.client else "0.0.0.0"

    # Only trust forwarding headers when the immediate peer is a known proxy.
    if not trusted_proxies or not ip_in_cidrs(direct_peer, trusted_proxies):
        return direct_peer

    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for:
        return direct_peer

    # X-Forwarded-For is "client, proxy1, proxy2" (left = original client).
    # The leftmost entries are attacker-controllable, so walk from the right
    # and skip trusted-proxy hops; the first untrusted address is the client.
    hops = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
    for ip in reversed(hops):
        if not ip_in_cidrs(ip, trusted_proxies):
            return ip

    # Entire chain is trusted proxies (or empty) — fall back to direct peer.
    return direct_peer


def ip_in_cidrs(
    ip_str: str, cidrs: List[str]
) -> bool:
    """Check if an IP address is within any of the given CIDR ranges.

    Args:
        ip_str: The IP address to check (IPv4 or IPv6 string).
        cidrs: List of CIDR notation strings to match against.

    Returns:
        True if the IP is within any of the CIDR ranges, False otherwise.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        # Invalid IP address format
        return False

    for cidr in cidrs:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            if ip in network:
                return True
        except ValueError:
            # Invalid CIDR format, skip it
            continue

    return False


class AccessLogMiddleware:
    """Pure ASGI middleware to log requests with X-Forwarded-For header.

    Logs each request showing both the direct client IP and the
    X-Forwarded-For header (if present) for debugging proxy setups.

    Attributes:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the access log middleware.

        Args:
            app: The ASGI application to wrap.
        """
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process ASGI requests and log access info.

        Args:
            scope: The ASGI connection scope.
            receive: The receive callable.
            send: The send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract request info
        request = Request(scope, receive, send)
        method = request.method
        path = request.url.path
        query = request.url.query
        full_path = f"{path}?{query}" if query else path

        # Get IPs
        direct_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For", "-")
        real_ip = get_client_ip(request)

        # Capture response status
        status_code = 0
        start_time = time.time()

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.time() - start_time) * 1000
            # Log with X-Forwarded-For info
            logger.info(
                f'{direct_ip} [fwd: {forwarded_for}] -> {real_ip} - "{method} {full_path}" {status_code} ({duration_ms:.0f}ms)'
            )


class IPAllowlistMiddleware:
    """Pure ASGI middleware to restrict access based on client IP addresses.

    This middleware checks incoming requests against a list of allowed
    CIDR ranges and returns a 403 Forbidden response for requests from
    IPs not in the allowlist.

    Uses pure ASGI style instead of BaseHTTPMiddleware to support SSE
    streaming without response buffering issues.

    The allowlist decision is made on the *direct TCP peer* by default.
    ``X-Forwarded-For`` is only consulted when the peer is within
    ``trusted_proxies`` (see :func:`get_client_ip`), so a spoofed header
    cannot bypass the allowlist (GHSA-2qvv-vjq9-g5r4).

    Attributes:
        app: The wrapped ASGI application.
        allowed_cidrs: List of allowed CIDR notation strings.
        trusted_proxies: CIDR ranges whose members are trusted to set
            X-Forwarded-For (default: none).

    Example:
        app.add_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["127.0.0.0/8", "160.79.104.0/21"],
            trusted_proxies=["127.0.0.1/32"],  # e.g. local reverse proxy
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_cidrs: List[str],
        trusted_proxies: Optional[List[str]] = None,
    ) -> None:
        """Initialize the IP allowlist middleware.

        Args:
            app: The ASGI application to wrap.
            allowed_cidrs: List of allowed CIDR notation strings.
            trusted_proxies: CIDR ranges whose members are trusted to set
                X-Forwarded-For. When empty (default), the header is ignored
                and the direct peer is used for the allowlist check.
        """
        self.app = app
        self.allowed_cidrs = allowed_cidrs
        self.trusted_proxies = trusted_proxies or []

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process ASGI requests and check IP against allowlist.

        Args:
            scope: The ASGI connection scope.
            receive: The receive callable.
            send: The send callable.
        """
        if scope["type"] != "http":
            # Pass through non-HTTP requests (websocket, lifespan, etc.)
            await self.app(scope, receive, send)
            return

        # Build a Request object to use get_client_ip helper
        request = Request(scope, receive, send)
        client_ip = get_client_ip(request, self.trusted_proxies)

        if not ip_in_cidrs(client_ip, self.allowed_cidrs):
            # Return 403 Forbidden
            response = Response(
                content=f"Forbidden: IP address {client_ip} is not allowed",
                status_code=403,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        # IP is allowed, pass through to app
        await self.app(scope, receive, send)


class TokenAuthMiddleware:
    """Pure ASGI middleware to require Bearer token authentication.

    This middleware validates that requests include a valid Bearer token
    in the Authorization header. If the token is invalid or missing,
    a 401 Unauthorized response is returned.

    Uses pure ASGI style instead of BaseHTTPMiddleware to support SSE
    streaming without response buffering issues.

    When no token is configured (token=None), all requests are allowed
    through without authentication.

    Attributes:
        app: The wrapped ASGI application.
        token: The required Bearer token, or None to disable authentication.

    Example:
        # Enable token authentication
        app.add_middleware(TokenAuthMiddleware, token="my-secret-token")

        # Disabled mode (allows all requests)
        app.add_middleware(TokenAuthMiddleware, token=None)

        # Combined with IP allowlist - middleware are processed in reverse order,
        # so add TokenAuth first (checked last), then IP allowlist (checked first)
        app.add_middleware(TokenAuthMiddleware, token="secret")
        app.add_middleware(IPAllowlistMiddleware, allowed_cidrs=LOCAL_CIDRS)
    """

    def __init__(
        self,
        app: ASGIApp,
        token: Optional[str],
    ) -> None:
        """Initialize the token authentication middleware.

        Args:
            app: The ASGI application to wrap.
            token: The required Bearer token, or None to disable authentication.
        """
        self.app = app
        self.token = token

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process ASGI requests and validate the Bearer token.

        Args:
            scope: The ASGI connection scope.
            receive: The receive callable.
            send: The send callable.
        """
        if scope["type"] != "http":
            # Pass through non-HTTP requests (websocket, lifespan, etc.)
            await self.app(scope, receive, send)
            return

        # If no token configured, allow all requests
        if self.token is None:
            await self.app(scope, receive, send)
            return

        # Build a Request object to access headers
        request = Request(scope, receive, send)

        # Get Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            response = Response(
                content="Unauthorized: Missing Authorization header",
                status_code=401,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        # Check for Bearer token format
        if not auth_header.startswith("Bearer "):
            response = Response(
                content="Unauthorized: Invalid Authorization header format (expected 'Bearer <token>')",
                status_code=401,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        # Extract and validate token
        provided_token = auth_header[7:]  # Remove "Bearer " prefix

        if provided_token != self.token:
            # Note: We intentionally don't log the actual token values
            response = Response(
                content="Unauthorized: Invalid token",
                status_code=401,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        # Token is valid, pass through to app
        await self.app(scope, receive, send)
