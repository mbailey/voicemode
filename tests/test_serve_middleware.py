"""Unit tests for VoiceMode serve middleware.

Tests for:
- IPAllowlistMiddleware - IP-based access control with CIDR support
- SecretPathMiddleware - Path-based secret authentication
- TokenAuthMiddleware - Bearer token authentication
- Helper functions: get_client_ip, ip_in_cidrs
"""

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from voice_mode.serve_middleware import (
    IPAllowlistMiddleware,
    SecretPathMiddleware,
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
    """Handler that echoes the client IP."""
    client_ip = get_client_ip(request)
    return PlainTextResponse(f"IP: {client_ip}")


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
    """Tests for the get_client_ip helper function."""

    def test_x_forwarded_for_single_ip(self):
        """Test X-Forwarded-For header with single IP."""
        app = Starlette(routes=[Route("/", echo_ip)])
        client = TestClient(app)

        response = client.get("/", headers={"X-Forwarded-For": "203.0.113.50"})
        assert response.text == "IP: 203.0.113.50"

    def test_x_forwarded_for_multiple_ips(self):
        """Test X-Forwarded-For header with multiple IPs (chain)."""
        app = Starlette(routes=[Route("/", echo_ip)])
        client = TestClient(app)

        # First IP should be used (the original client)
        response = client.get(
            "/",
            headers={"X-Forwarded-For": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        )
        assert response.text == "IP: 203.0.113.50"

    def test_x_forwarded_for_with_spaces(self):
        """Test X-Forwarded-For header with extra spaces."""
        app = Starlette(routes=[Route("/", echo_ip)])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={"X-Forwarded-For": "  203.0.113.50  ,  70.41.3.18  "}
        )
        assert response.text == "IP: 203.0.113.50"

    def test_fallback_to_request_client(self):
        """Test fallback to request.client when no X-Forwarded-For."""
        app = Starlette(routes=[Route("/", echo_ip)])
        client = TestClient(app)

        # TestClient uses testclient as the client, which results in a specific host
        response = client.get("/")
        # The exact IP depends on TestClient implementation, but it should not be empty
        assert "IP:" in response.text
        # Should NOT be 0.0.0.0 since TestClient provides a client
        assert response.text != "IP: 0.0.0.0"


# =============================================================================
# Tests for IPAllowlistMiddleware
# =============================================================================


class TestIPAllowlistMiddleware:
    """Tests for IP allowlist middleware."""

    def test_allowed_ip_passes_through(self):
        """Test that allowed IP addresses pass through."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["203.0.113.0/24"]
        )
        client = TestClient(app)

        response = client.get("/", headers={"X-Forwarded-For": "203.0.113.50"})
        assert response.status_code == 200
        assert response.text == "OK"

    def test_denied_ip_returns_403(self):
        """Test that denied IP addresses get 403 response."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["192.168.0.0/16"]
        )
        client = TestClient(app)

        response = client.get("/", headers={"X-Forwarded-For": "8.8.8.8"})
        assert response.status_code == 403
        assert "Forbidden" in response.text
        assert "8.8.8.8" in response.text

    def test_localhost_allowed(self):
        """Test localhost IP in LOCAL_CIDRS."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=LOCAL_CIDRS
        )
        client = TestClient(app)

        response = client.get("/", headers={"X-Forwarded-For": "127.0.0.1"})
        assert response.status_code == 200

    def test_cidr_range_allows_multiple_ips(self):
        """Test that CIDR range allows all IPs in the range."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["10.0.0.0/8"]
        )
        client = TestClient(app)

        # All these should be allowed
        for ip in ["10.0.0.1", "10.255.255.255", "10.128.64.32"]:
            response = client.get("/", headers={"X-Forwarded-For": ip})
            assert response.status_code == 200, f"IP {ip} should be allowed"

    def test_ipv6_allowed(self):
        """Test IPv6 address in allowlist."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["::1/128", "2001:db8::/32"]
        )
        client = TestClient(app)

        response = client.get("/", headers={"X-Forwarded-For": "::1"})
        assert response.status_code == 200

        response = client.get("/", headers={"X-Forwarded-For": "2001:db8::1"})
        assert response.status_code == 200

    def test_ipv6_denied(self):
        """Test IPv6 address not in allowlist."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=["::1/128"]
        )
        client = TestClient(app)

        response = client.get("/", headers={"X-Forwarded-For": "2001:db8::1"})
        assert response.status_code == 403

    def test_empty_allowlist_denies_all(self):
        """Test that empty allowlist denies all IPs."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=[]
        )
        client = TestClient(app)

        for ip in ["127.0.0.1", "192.168.1.1", "8.8.8.8"]:
            response = client.get("/", headers={"X-Forwarded-For": ip})
            assert response.status_code == 403, f"IP {ip} should be denied with empty allowlist"

    def test_anthropic_cidrs_allowed(self):
        """Test that Anthropic CIDRs work correctly."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=ANTHROPIC_CIDRS
        )
        client = TestClient(app)

        # IP in Anthropic's primary range
        response = client.get("/", headers={"X-Forwarded-For": "160.79.104.100"})
        assert response.status_code == 200

        # Legacy Anthropic IP
        response = client.get("/", headers={"X-Forwarded-For": "35.193.26.195"})
        assert response.status_code == 200

        # Not an Anthropic IP
        response = client.get("/", headers={"X-Forwarded-For": "8.8.8.8"})
        assert response.status_code == 403

    def test_combined_local_and_anthropic_cidrs(self):
        """Test combined LOCAL_CIDRS and ANTHROPIC_CIDRS."""
        app = create_app_with_middleware(
            IPAllowlistMiddleware,
            allowed_cidrs=LOCAL_CIDRS + ANTHROPIC_CIDRS
        )
        client = TestClient(app)

        # Local IP
        response = client.get("/", headers={"X-Forwarded-For": "192.168.1.100"})
        assert response.status_code == 200

        # Anthropic IP
        response = client.get("/", headers={"X-Forwarded-For": "160.79.105.50"})
        assert response.status_code == 200

        # External IP
        response = client.get("/", headers={"X-Forwarded-For": "8.8.8.8"})
        assert response.status_code == 403


# =============================================================================
# Tests for SecretPathMiddleware
# =============================================================================


class TestSecretPathMiddleware:
    """Tests for secret path middleware."""

    def test_correct_secret_allows_access(self):
        """Test that correct secret in path allows access."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="my-secret-uuid",
            base_path="/sse"
        )
        client = TestClient(app)

        response = client.get("/sse/my-secret-uuid")
        assert response.status_code == 200
        assert response.text == "OK"

    def test_correct_secret_with_subpath(self):
        """Test that correct secret with additional path segments works."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="my-secret-uuid",
            base_path="/sse"
        )
        client = TestClient(app)

        response = client.get("/sse/my-secret-uuid/messages")
        assert response.status_code == 200

    def test_wrong_secret_returns_404(self):
        """Test that wrong secret returns 404 (not 403!)."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="correct-secret",
            base_path="/sse"
        )
        client = TestClient(app)

        response = client.get("/sse/wrong-secret")
        assert response.status_code == 404
        assert "Not Found" in response.text

    def test_base_path_without_secret_returns_404(self):
        """Test that base path without secret returns 404."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="my-secret",
            base_path="/sse"
        )
        client = TestClient(app)

        response = client.get("/sse")
        assert response.status_code == 404

    def test_no_secret_configured_allows_all(self):
        """Test that None secret allows all requests."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret=None,
            base_path="/sse"
        )
        client = TestClient(app)

        response = client.get("/sse")
        assert response.status_code == 200

        response = client.get("/sse/anything")
        assert response.status_code == 200

    def test_paths_not_under_base_path_pass_through(self):
        """Test that paths not under base_path pass through without auth."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="my-secret",
            base_path="/sse"
        )
        client = TestClient(app)

        # Other paths should work without secret
        response = client.get("/")
        assert response.status_code == 200

        response = client.get("/other")
        assert response.status_code == 200

    def test_partial_secret_match_fails(self):
        """Test that partial secret match returns 404."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="my-secret-uuid",
            base_path="/sse"
        )
        client = TestClient(app)

        # Partial match should fail
        response = client.get("/sse/my-secret")
        assert response.status_code == 404

        response = client.get("/sse/my-secret-uuid-extra")
        assert response.status_code == 404

    def test_secret_as_prefix_of_another_path(self):
        """Test that secret must match exactly, not be a prefix."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="secret",
            base_path="/sse"
        )
        client = TestClient(app)

        # Exact match works
        response = client.get("/sse/secret")
        assert response.status_code == 200

        # Secret followed by slash and path works
        response = client.get("/sse/secret/more")
        assert response.status_code == 200

        # Secret as prefix of longer word fails
        response = client.get("/sse/secretword")
        assert response.status_code == 404

    def test_base_path_trailing_slash_normalized(self):
        """Test that base_path with trailing slash is normalized."""
        app = create_app_with_middleware(
            SecretPathMiddleware,
            secret="mysecret",
            base_path="/sse/"  # Trailing slash
        )
        client = TestClient(app)

        response = client.get("/sse/mysecret")
        assert response.status_code == 200


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
        client = TestClient(app)

        # Both valid - should work
        response = client.get(
            "/",
            headers={
                "X-Forwarded-For": "192.168.1.100",
                "Authorization": "Bearer my-token"
            }
        )
        assert response.status_code == 200

    def test_ip_allowed_but_token_invalid(self):
        """Test that valid IP but invalid token fails."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": ["192.168.0.0/16"]}),
            (TokenAuthMiddleware, {"token": "correct-token"}),
        ])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "X-Forwarded-For": "192.168.1.100",
                "Authorization": "Bearer wrong-token"
            }
        )
        assert response.status_code == 401

    def test_token_valid_but_ip_denied(self):
        """Test that valid token but denied IP fails."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": ["192.168.0.0/16"]}),
            (TokenAuthMiddleware, {"token": "my-token"}),
        ])
        client = TestClient(app)

        response = client.get(
            "/",
            headers={
                "X-Forwarded-For": "8.8.8.8",  # Not in allowlist
                "Authorization": "Bearer my-token"
            }
        )
        assert response.status_code == 403

    def test_ip_allowlist_and_secret_path(self):
        """Test IP allowlist combined with secret path."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": ["10.0.0.0/8"]}),
            (SecretPathMiddleware, {"secret": "my-secret", "base_path": "/sse"}),
        ])
        client = TestClient(app)

        # Both valid
        response = client.get(
            "/sse/my-secret",
            headers={"X-Forwarded-For": "10.1.2.3"}
        )
        assert response.status_code == 200

        # IP valid, wrong secret
        response = client.get(
            "/sse/wrong-secret",
            headers={"X-Forwarded-For": "10.1.2.3"}
        )
        assert response.status_code == 404

        # Secret valid, IP denied
        response = client.get(
            "/sse/my-secret",
            headers={"X-Forwarded-For": "8.8.8.8"}
        )
        assert response.status_code == 403

    def test_all_three_middlewares(self):
        """Test all three middlewares together."""
        app = create_app_with_multiple_middleware([
            (IPAllowlistMiddleware, {"allowed_cidrs": LOCAL_CIDRS}),
            (SecretPathMiddleware, {"secret": "secret123", "base_path": "/sse"}),
            (TokenAuthMiddleware, {"token": "token456"}),
        ])
        client = TestClient(app)

        # All valid
        response = client.get(
            "/sse/secret123",
            headers={
                "X-Forwarded-For": "127.0.0.1",
                "Authorization": "Bearer token456"
            }
        )
        assert response.status_code == 200

        # Non-protected path still needs IP and token
        response = client.get(
            "/",
            headers={
                "X-Forwarded-For": "127.0.0.1",
                "Authorization": "Bearer token456"
            }
        )
        assert response.status_code == 200

        # Protected path without secret
        response = client.get(
            "/sse",
            headers={
                "X-Forwarded-For": "127.0.0.1",
                "Authorization": "Bearer token456"
            }
        )
        assert response.status_code == 404
