"""Unit tests for VoiceMode serve middleware.

Tests for:
- IPAllowlistMiddleware - IP-based access control with CIDR support
- TokenAuthMiddleware - Bearer token authentication
- Helper functions: get_client_ip, ip_in_cidrs
"""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from voice_mode.serve_middleware import (
    IPAllowlistMiddleware,
    TokenAuthMiddleware,
    get_client_ip,
    ip_in_cidrs,
    ANTHROPIC_CIDRS,
    LOCAL_CIDRS,
)


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


def homepage(request):
    """Simple handler that returns OK."""
    return PlainTextResponse("OK")


def echo_ip(request):
    """Handler that echoes the client IP (no trusted proxies)."""
    client_ip = get_client_ip(request)
    return PlainTextResponse(f"IP: {client_ip}")


def make_request(client_host, headers=None):
    """Build a minimal Starlette Request for get_client_ip unit tests.

    Args:
        client_host: The direct TCP peer host, or None for no client.
        headers: Optional dict of header name -> value.

    Returns:
        A starlette.requests.Request with the given peer and headers.
    """
    headers = headers or {}
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in headers.items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def create_app_with_middleware(middleware_class, routes=None, **kwargs):
    """Create a test app with the specified middleware."""
    if routes is None:
        routes = [
            Route("/", homepage),
            Route("/sse", homepage),
            Route("/sse/{path:path}", homepage),
            Route("/other", homepage),
        ]
    app = Starlette(routes=routes)
    app.add_middleware(middleware_class, **kwargs)
    return app


def create_app_with_multiple_middleware(middleware_configs, routes=None):
    """Create a test app with multiple middlewares.

    Args:
        middleware_configs: List of (middleware_class, kwargs) tuples.
                           Applied in order (first in list = outermost).
    """
    if routes is None:
        routes = [
            Route("/", homepage),
            Route("/sse", homepage),
            Route("/sse/{path:path}", homepage),
        ]
    app = Starlette(routes=routes)
    # Starlette processes middleware in reverse order of addition
    # So we reverse our list to get the expected order
    for middleware_class, kwargs in reversed(middleware_configs):
        app.add_middleware(middleware_class, **kwargs)
    return app


# =============================================================================
# Tests for ip_in_cidrs function
# =============================================================================


class TestIpInCidrs:
    """Tests for the ip_in_cidrs helper function."""

    def test_ip_in_cidr_range(self):
        """Test that IP within CIDR range returns True."""
        assert ip_in_cidrs("192.168.1.100", ["192.168.0.0/16"]) is True
        assert ip_in_cidrs("10.0.0.1", ["10.0.0.0/8"]) is True
        assert ip_in_cidrs("172.16.5.10", ["172.16.0.0/12"]) is True

    def test_ip_not_in_cidr_range(self):
        """Test that IP outside CIDR range returns False."""
        assert ip_in_cidrs("192.168.1.100", ["10.0.0.0/8"]) is False
        assert ip_in_cidrs("8.8.8.8", ["192.168.0.0/16"]) is False
        assert ip_in_cidrs("1.2.3.4", ["172.16.0.0/12"]) is False

    def test_ip_exact_match_single_ip_cidr(self):
        """Test IP matching against /32 CIDR (single IP)."""
        assert ip_in_cidrs("35.193.26.195", ["35.193.26.195/32"]) is True
        assert ip_in_cidrs("35.193.26.196", ["35.193.26.195/32"]) is False

    def test_ip_in_multiple_cidrs(self):
        """Test IP against multiple CIDR ranges."""
        cidrs = ["10.0.0.0/8", "192.168.0.0/16"]
        assert ip_in_cidrs("10.1.2.3", cidrs) is True
        assert ip_in_cidrs("192.168.50.1", cidrs) is True
        assert ip_in_cidrs("8.8.8.8", cidrs) is False

    def test_ipv6_in_cidr_range(self):
        """Test IPv6 address in CIDR range."""
        assert ip_in_cidrs("::1", ["::1/128"]) is True
        assert ip_in_cidrs("fe80::1", ["fe80::/10"]) is True
        assert ip_in_cidrs("2001:db8::1", ["2001:db8::/32"]) is True

    def test_ipv6_not_in_cidr_range(self):
        """Test IPv6 address not in CIDR range."""
        assert ip_in_cidrs("::2", ["::1/128"]) is False
        assert ip_in_cidrs("2001:db8::1", ["fe80::/10"]) is False

    def test_invalid_ip_format(self):
        """Test that invalid IP format returns False."""
        assert ip_in_cidrs("not-an-ip", ["192.168.0.0/16"]) is False
        assert ip_in_cidrs("256.256.256.256", ["192.168.0.0/16"]) is False
        assert ip_in_cidrs("", ["192.168.0.0/16"]) is False
        assert ip_in_cidrs("192.168.1", ["192.168.0.0/16"]) is False

    def test_invalid_cidr_format_skipped(self):
        """Test that invalid CIDR formats are skipped without error."""
        # Invalid CIDRs are skipped, valid ones still work
        cidrs = ["not-a-cidr", "192.168.0.0/16", "also-invalid"]
        assert ip_in_cidrs("192.168.1.1", cidrs) is True
        assert ip_in_cidrs("10.0.0.1", cidrs) is False

    def test_empty_cidr_list(self):
        """Test that empty CIDR list returns False for any IP."""
        assert ip_in_cidrs("192.168.1.1", []) is False
        assert ip_in_cidrs("127.0.0.1", []) is False

    def test_localhost_in_local_cidrs(self):
        """Test localhost addresses against LOCAL_CIDRS constant."""
        assert ip_in_cidrs("127.0.0.1", LOCAL_CIDRS) is True
        assert ip_in_cidrs("127.255.255.255", LOCAL_CIDRS) is True
        assert ip_in_cidrs("::1", LOCAL_CIDRS) is True

    def test_private_networks_in_local_cidrs(self):
        """Test private network addresses against LOCAL_CIDRS constant."""
        # Class A private
        assert ip_in_cidrs("10.0.0.1", LOCAL_CIDRS) is True
        assert ip_in_cidrs("10.255.255.255", LOCAL_CIDRS) is True
        # Class B private
        assert ip_in_cidrs("172.16.0.1", LOCAL_CIDRS) is True
        assert ip_in_cidrs("172.31.255.255", LOCAL_CIDRS) is True
        # Class C private
        assert ip_in_cidrs("192.168.0.1", LOCAL_CIDRS) is True
        assert ip_in_cidrs("192.168.255.255", LOCAL_CIDRS) is True

    def test_anthropic_cidrs(self):
        """Test IPs against ANTHROPIC_CIDRS constant."""
        # Primary range
        assert ip_in_cidrs("160.79.104.1", ANTHROPIC_CIDRS) is True
        assert ip_in_cidrs("160.79.111.254", ANTHROPIC_CIDRS) is True
        # Legacy IPs
        assert ip_in_cidrs("35.193.26.195", ANTHROPIC_CIDRS) is True
        assert ip_in_cidrs("35.202.227.108", ANTHROPIC_CIDRS) is True
        # Not in Anthropic range
        assert ip_in_cidrs("8.8.8.8", ANTHROPIC_CIDRS) is False


# =============================================================================
# Tests for get_client_ip function
# =============================================================================


class TestGetClientIp:
    """Tests for the get_client_ip helper function.

    Security model (GHSA-2qvv-vjq9-g5r4): X-Forwarded-For is only honored
    when the direct TCP peer is within trusted_proxies. Otherwise the direct
    peer is returned and the header is ignored.
    """

    # --- Without trusted proxies: header must be ignored -----------------

    def test_xff_ignored_when_no_trusted_proxies(self):
        """X-Forwarded-For is ignored entirely without trusted_proxies."""
        request = make_request("8.8.8.8", {"X-Forwarded-For": "127.0.0.1"})
        assert get_client_ip(request) == "8.8.8.8"
        assert get_client_ip(request, trusted_proxies=[]) == "8.8.8.8"

    def test_direct_peer_used_when_no_header(self):
        """Direct peer is returned when no X-Forwarded-For is present."""
        request = make_request("203.0.113.50")
        assert get_client_ip(request) == "203.0.113.50"

    def test_no_client_falls_back_to_zero(self):
        """Missing request.client yields the 0.0.0.0 fallback."""
        request = make_request(None, {"X-Forwarded-For": "127.0.0.1"})
        assert get_client_ip(request) == "0.0.0.0"

    def test_spoofed_xff_does_not_override_peer(self):
        """A spoofed allowed IP in XFF does not override an untrusted peer."""
        request = make_request("8.8.8.8", {"X-Forwarded-For": "10.0.0.5"})
        # Peer is untrusted, so the real peer wins regardless of the header.
        assert get_client_ip(request, trusted_proxies=["127.0.0.1/32"]) == "8.8.8.8"

    # --- With trusted proxies: header honored for trusted peers ----------

    def test_xff_honored_from_trusted_proxy(self):
        """XFF is honored when the direct peer is a trusted proxy."""
        request = make_request("127.0.0.1", {"X-Forwarded-For": "203.0.113.50"})
        assert get_client_ip(request, trusted_proxies=["127.0.0.1/32"]) == "203.0.113.50"

    def test_xff_chain_walks_right_to_left(self):
        """The first untrusted hop (from the right) is the real client."""
        # client, then two trusted proxies appended on the way in.
        request = make_request(
            "127.0.0.1",
            {"X-Forwarded-For": "203.0.113.50, 127.0.0.2, 127.0.0.3"},
        )
        proxies = ["127.0.0.0/8"]
        # Peer 127.0.0.1 trusted; walk right skipping 127.* hops -> 203.0.113.50
        assert get_client_ip(request, trusted_proxies=proxies) == "203.0.113.50"

    def test_xff_with_spaces_trusted(self):
        """Whitespace in the chain is stripped when peer is trusted."""
        request = make_request(
            "127.0.0.1",
            {"X-Forwarded-For": "  203.0.113.50  ,  127.0.0.2  "},
        )
        assert get_client_ip(request, trusted_proxies=["127.0.0.0/8"]) == "203.0.113.50"

    def test_all_trusted_chain_falls_back_to_peer(self):
        """If every hop is trusted, fall back to the direct peer."""
        request = make_request(
            "127.0.0.1",
            {"X-Forwarded-For": "127.0.0.2, 127.0.0.3"},
        )
        assert get_client_ip(request, trusted_proxies=["127.0.0.0/8"]) == "127.0.0.1"

    def test_trusted_peer_without_header_uses_peer(self):
        """Trusted peer but no XFF header returns the peer itself."""
        request = make_request("127.0.0.1")
        assert get_client_ip(request, trusted_proxies=["127.0.0.1/32"]) == "127.0.0.1"


# =============================================================================
# Tests for IPAllowlistMiddleware
# =============================================================================


def allowlist_client(allowed_cidrs, peer, trusted_proxies=None):
    """Build a TestClient whose direct TCP peer is `peer`."""
    app = create_app_with_middleware(
        IPAllowlistMiddleware,
        allowed_cidrs=allowed_cidrs,
        trusted_proxies=trusted_proxies or [],
    )
    return TestClient(app, client=(peer, 12345))


class TestIPAllowlistMiddleware:
    """Tests for IP allowlist middleware (decides on the direct TCP peer)."""

    def test_allowed_ip_passes_through(self):
        """Test that an allowed direct peer passes through."""
        client = allowlist_client(["203.0.113.0/24"], peer="203.0.113.50")
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "OK"

    def test_denied_ip_returns_403(self):
        """Test that a denied direct peer gets a 403 response."""
        client = allowlist_client(["192.168.0.0/16"], peer="8.8.8.8")
        response = client.get("/")
        assert response.status_code == 403
        assert "Forbidden" in response.text
        assert "8.8.8.8" in response.text

    def test_localhost_allowed(self):
        """Test localhost peer in LOCAL_CIDRS."""
        client = allowlist_client(LOCAL_CIDRS, peer="127.0.0.1")
        assert client.get("/").status_code == 200

    def test_cidr_range_allows_multiple_ips(self):
        """Test that CIDR range allows all peers in the range."""
        for ip in ["10.0.0.1", "10.255.255.255", "10.128.64.32"]:
            client = allowlist_client(["10.0.0.0/8"], peer=ip)
            assert client.get("/").status_code == 200, f"IP {ip} should be allowed"

    def test_ipv6_allowed(self):
        """Test IPv6 peer in allowlist."""
        client = allowlist_client(["::1/128", "2001:db8::/32"], peer="::1")
        assert client.get("/").status_code == 200

        client = allowlist_client(["::1/128", "2001:db8::/32"], peer="2001:db8::1")
        assert client.get("/").status_code == 200

    def test_ipv6_denied(self):
        """Test IPv6 peer not in allowlist."""
        client = allowlist_client(["::1/128"], peer="2001:db8::1")
        assert client.get("/").status_code == 403

    def test_empty_allowlist_denies_all(self):
        """Test that empty allowlist denies all peers."""
        for ip in ["127.0.0.1", "192.168.1.1", "8.8.8.8"]:
            client = allowlist_client([], peer=ip)
            assert client.get("/").status_code == 403, f"IP {ip} should be denied"

    def test_anthropic_cidrs_allowed(self):
        """Test that Anthropic CIDRs work correctly on the direct peer."""
        client = allowlist_client(ANTHROPIC_CIDRS, peer="160.79.104.100")
        assert client.get("/").status_code == 200

        client = allowlist_client(ANTHROPIC_CIDRS, peer="35.193.26.195")
        assert client.get("/").status_code == 200

        client = allowlist_client(ANTHROPIC_CIDRS, peer="8.8.8.8")
        assert client.get("/").status_code == 403

    def test_combined_local_and_anthropic_cidrs(self):
        """Test combined LOCAL_CIDRS and ANTHROPIC_CIDRS."""
        cidrs = LOCAL_CIDRS + ANTHROPIC_CIDRS
        assert allowlist_client(cidrs, peer="192.168.1.100").get("/").status_code == 200
        assert allowlist_client(cidrs, peer="160.79.105.50").get("/").status_code == 200
        assert allowlist_client(cidrs, peer="8.8.8.8").get("/").status_code == 403

    # --- Regression tests for GHSA-2qvv-vjq9-g5r4 (XFF allowlist bypass) ---

    def test_spoofed_xff_does_not_bypass_allowlist(self):
        """A spoofed X-Forwarded-For from an untrusted peer must NOT bypass.

        This is the core vulnerability: an attacker at 8.8.8.8 sends
        X-Forwarded-For: 127.0.0.1 (an allowed IP) hoping to be let in.
        With no trusted proxies, the header is ignored and the real peer
        (8.8.8.8) is denied.
        """
        client = allowlist_client(LOCAL_CIDRS, peer="8.8.8.8")
        response = client.get("/", headers={"X-Forwarded-For": "127.0.0.1"})
        assert response.status_code == 403
        assert "8.8.8.8" in response.text

    def test_spoofed_xff_with_allowed_cidr_denied(self):
        """Spoofing an IP inside an allowed CIDR from an untrusted peer fails."""
        client = allowlist_client(["10.0.0.0/8"], peer="203.0.113.99")
        response = client.get("/", headers={"X-Forwarded-For": "10.1.2.3"})
        assert response.status_code == 403

    def test_xff_honored_from_trusted_proxy(self):
        """Behind a trusted proxy, an allowed forwarded client is permitted."""
        client = allowlist_client(
            ["203.0.113.0/24"], peer="127.0.0.1", trusted_proxies=["127.0.0.1/32"]
        )
        response = client.get("/", headers={"X-Forwarded-For": "203.0.113.50"})
        assert response.status_code == 200

    def test_xff_from_trusted_proxy_disallowed_client_denied(self):
        """Behind a trusted proxy, a disallowed forwarded client is denied."""
        client = allowlist_client(
            ["203.0.113.0/24"], peer="127.0.0.1", trusted_proxies=["127.0.0.1/32"]
        )
        response = client.get("/", headers={"X-Forwarded-For": "8.8.8.8"})
        assert response.status_code == 403
        assert "8.8.8.8" in response.text

    def test_untrusted_peer_cannot_forge_even_with_trusted_proxies_set(self):
        """An untrusted peer's XFF is ignored even when trusted_proxies exist."""
        # Trusted proxy is 127.0.0.1, but the attacker connects from 8.8.8.8.
        client = allowlist_client(
            ["203.0.113.0/24"], peer="8.8.8.8", trusted_proxies=["127.0.0.1/32"]
        )
        response = client.get("/", headers={"X-Forwarded-For": "203.0.113.50"})
        assert response.status_code == 403


# =============================================================================
# Tests for TokenAuthMiddleware
# =============================================================================


class TestTokenAuthMiddleware:
    """Tests for token authentication middleware."""

    def test_valid_bearer_token_allows_access(self):
        """Test that valid Bearer token allows access."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token="my-secret-token"
        )
        client = TestClient(app)

        response = client.get("/", headers={"Authorization": "Bearer my-secret-token"})
        assert response.status_code == 200
        assert response.text == "OK"

    def test_invalid_token_returns_401(self):
        """Test that invalid token returns 401."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token="correct-token"
        )
        client = TestClient(app)

        response = client.get("/", headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401
        assert "Invalid token" in response.text

    def test_missing_authorization_header_returns_401(self):
        """Test that missing Authorization header returns 401."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token="my-token"
        )
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 401
        assert "Missing Authorization header" in response.text

    def test_wrong_auth_format_returns_401(self):
        """Test that non-Bearer format returns 401."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token="my-token"
        )
        client = TestClient(app)

        # Basic auth format
        response = client.get("/", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert response.status_code == 401
        assert "Invalid Authorization header format" in response.text

        # Just the token without Bearer prefix
        response = client.get("/", headers={"Authorization": "my-token"})
        assert response.status_code == 401

    def test_no_token_configured_allows_all(self):
        """Test that None token allows all requests."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token=None
        )
        client = TestClient(app)

        # No auth header - should still work
        response = client.get("/")
        assert response.status_code == 200

        # With random auth header - should still work
        response = client.get("/", headers={"Authorization": "Bearer anything"})
        assert response.status_code == 200

    def test_bearer_case_sensitive(self):
        """Test that 'Bearer' prefix is case-sensitive."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token="my-token"
        )
        client = TestClient(app)

        # Lowercase 'bearer' should fail
        response = client.get("/", headers={"Authorization": "bearer my-token"})
        assert response.status_code == 401

        # Uppercase 'BEARER' should fail
        response = client.get("/", headers={"Authorization": "BEARER my-token"})
        assert response.status_code == 401

    def test_empty_token_after_bearer(self):
        """Test that empty token after Bearer fails."""
        app = create_app_with_middleware(
            TokenAuthMiddleware,
            token="my-token"
        )
        client = TestClient(app)

        response = client.get("/", headers={"Authorization": "Bearer "})
        assert response.status_code == 401


# =============================================================================
# Tests for Middleware Combinations
# =============================================================================


class TestMiddlewareCombinations:
    """Tests for combining multiple middlewares."""

    def test_ip_allowlist_and_token_both_pass(self):
        """Test that both IP and token must be valid."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": ["192.168.0.0/16"]}),
            (TokenAuthMiddleware, {"token": "my-token"}),
        ])
        client = TestClient(app, client=("192.168.1.100", 12345))

        # Both valid - should work
        response = client.get("/", headers={"Authorization": "Bearer my-token"})
        assert response.status_code == 200

    def test_ip_allowed_but_token_invalid(self):
        """Test that valid IP but invalid token fails."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": ["192.168.0.0/16"]}),
            (TokenAuthMiddleware, {"token": "correct-token"}),
        ])
        client = TestClient(app, client=("192.168.1.100", 12345))

        response = client.get("/", headers={"Authorization": "Bearer wrong-token"})
        assert response.status_code == 401

    def test_token_valid_but_ip_denied(self):
        """Test that valid token but denied IP fails."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": ["192.168.0.0/16"]}),
            (TokenAuthMiddleware, {"token": "my-token"}),
        ])
        client = TestClient(app, client=("8.8.8.8", 12345))  # Not in allowlist

        response = client.get("/", headers={"Authorization": "Bearer my-token"})
        assert response.status_code == 403
