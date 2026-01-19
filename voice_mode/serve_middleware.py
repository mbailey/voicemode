"""Middleware for VoiceMode HTTP/SSE server.

This module provides middleware to restrict access to the VoiceMode server:

1. IPAllowlistMiddleware - Restrict access based on client IP addresses.
   Supports CIDR notation for flexible IP range configuration and handles
   X-Forwarded-For headers for proxied requests.

2. SecretPathMiddleware - Require a secret path segment for access.
   Provides simple authentication by requiring a pre-shared secret in the URL.

3. TokenAuthMiddleware - Bearer token authentication via Authorization header.
   Validates Bearer tokens for API-style authentication.

Usage:
    from voice_mode.serve_middleware import (
        IPAllowlistMiddleware,
        SecretPathMiddleware,
        TokenAuthMiddleware,
        ANTHROPIC_CIDRS,
        LOCAL_CIDRS,
    )

    # Allow localhost + Anthropic IPs
    allowed = LOCAL_CIDRS + ANTHROPIC_CIDRS
    app.add_middleware(IPAllowlistMiddleware, allowed_cidrs=allowed)

    # Require secret path: /sse/my-secret-uuid
    app.add_middleware(SecretPathMiddleware, secret="my-secret-uuid", base_path="/sse")

    # Require Bearer token authentication
    app.add_middleware(TokenAuthMiddleware, token="my-secret-token")
"""

import ipaddress
from typing import Callable, List, Optional, Union

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send


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

# Local and private network ranges
LOCAL_CIDRS: List[str] = [
    "127.0.0.0/8",      # IPv4 localhost
    "10.0.0.0/8",       # Private Class A
    "172.16.0.0/12",    # Private Class B
    "192.168.0.0/16",   # Private Class C
    "::1/128",          # IPv6 localhost
]


def get_client_ip(request: Request) -> str:
    """Extract the real client IP address from a request.

    Handles X-Forwarded-For header for proxied requests (e.g., behind
    Tailscale Funnel or other reverse proxies). Takes the first IP in
    the chain, which is the original client IP.

    Args:
        request: The Starlette request object.

    Returns:
        The client IP address as a string.
    """
    # Check X-Forwarded-For header first (for proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        # The first IP is the original client
        client_ip = forwarded_for.split(",")[0].strip()
        return client_ip

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    # Last resort fallback
    return "0.0.0.0"


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


class IPAllowlistMiddleware:
    """Pure ASGI middleware to restrict access based on client IP addresses.

    This middleware checks incoming requests against a list of allowed
    CIDR ranges and returns a 403 Forbidden response for requests from
    IPs not in the allowlist.

    Uses pure ASGI style instead of BaseHTTPMiddleware to support SSE
    streaming without response buffering issues.

    Attributes:
        app: The wrapped ASGI application.
        allowed_cidrs: List of allowed CIDR notation strings.

    Example:
        app.add_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["127.0.0.0/8", "160.79.104.0/21"]
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_cidrs: List[str],
    ) -> None:
        """Initialize the IP allowlist middleware.

        Args:
            app: The ASGI application to wrap.
            allowed_cidrs: List of allowed CIDR notation strings.
        """
        self.app = app
        self.allowed_cidrs = allowed_cidrs

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
        client_ip = get_client_ip(request)

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


class SecretPathMiddleware:
    """Pure ASGI middleware to require a secret path segment for access.

    This middleware validates that requests include the correct secret
    in the URL path. If the secret is incorrect or missing, a 404 Not Found
    response is returned (not 403, to avoid revealing that the endpoint exists).

    Uses pure ASGI style instead of BaseHTTPMiddleware to support SSE
    streaming without response buffering issues.

    The secret acts as a pre-shared key in the URL. For example:
    - Without secret: /sse
    - With secret: /sse/my-secret-uuid

    Attributes:
        app: The wrapped ASGI application.
        secret: The required secret path segment, or None to disable.
        base_path: The base path that requires authentication (e.g., "/sse").

    Example:
        # Enable secret path authentication
        app.add_middleware(
            SecretPathMiddleware,
            secret="my-secret-uuid",
            base_path="/sse"
        )

        # Disabled mode (allows all requests)
        app.add_middleware(
            SecretPathMiddleware,
            secret=None,
            base_path="/sse"
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        secret: Optional[str],
        base_path: str = "/sse",
    ) -> None:
        """Initialize the secret path middleware.

        Args:
            app: The ASGI application to wrap.
            secret: The required secret path segment, or None to disable auth.
            base_path: The base path that requires authentication.
        """
        self.app = app
        self.secret = secret
        self.base_path = base_path.rstrip("/")  # Normalize: remove trailing slash

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process ASGI requests and validate the secret path.

        Args:
            scope: The ASGI connection scope.
            receive: The receive callable.
            send: The send callable.
        """
        if scope["type"] != "http":
            # Pass through non-HTTP requests (websocket, lifespan, etc.)
            await self.app(scope, receive, send)
            return

        # If no secret configured, allow all requests
        if self.secret is None:
            await self.app(scope, receive, send)
            return

        request_path = scope.get("path", "")

        # Check if request is for the protected base path
        if request_path == self.base_path or request_path.startswith(self.base_path + "/"):
            # Expected path with secret: {base_path}/{secret} or {base_path}/{secret}/...
            expected_prefix = f"{self.base_path}/{self.secret}"

            # Path must match exactly or start with expected_prefix followed by /
            if request_path == expected_prefix or request_path.startswith(expected_prefix + "/"):
                # Rewrite path to strip the secret segment before forwarding
                # e.g., /sse/secret -> /sse, /sse/secret/foo -> /sse/foo
                new_path = self.base_path + request_path[len(expected_prefix):]
                # Ensure we have at least the base path
                if not new_path:
                    new_path = self.base_path
                scope["path"] = new_path
                await self.app(scope, receive, send)
                return

            # Wrong secret or no secret - return 404 to avoid revealing endpoint
            # Note: We intentionally don't log the actual secret value
            response = Response(
                content="Not Found",
                status_code=404,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        # Request is not for the protected path, allow it through
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
