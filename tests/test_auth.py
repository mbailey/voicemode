"""
Unit tests for voice_mode.auth module.

Tests PKCE generation, token storage, port selection, and OAuth flow components.
"""

import base64
import hashlib
import os
import socket
import time
from unittest.mock import MagicMock, patch

import pytest

from voice_mode.auth import (
    AUTH0_DOMAIN,
    AUTH0_CLIENT_ID,
    CALLBACK_PORT_START,
    CALLBACK_PORT_END,
    AuthError,
    CallbackServer,
    Credentials,
    PKCEParams,
    build_authorize_url,
    clear_credentials,
    exchange_code_for_tokens,
    find_available_port,
    format_expiry,
    generate_pkce_params,
    get_user_info,
    get_valid_credentials,
    load_credentials,
    refresh_access_token,
    save_credentials,
)


class TestPKCE:
    """Test PKCE code_verifier and code_challenge generation."""

    def test_generate_pkce_params_returns_valid_structure(self):
        """Test that generate_pkce_params returns a PKCEParams object."""
        pkce = generate_pkce_params()

        assert isinstance(pkce, PKCEParams)
        assert pkce.code_verifier is not None
        assert pkce.code_challenge is not None
        assert pkce.code_challenge_method == "S256"

    def test_code_verifier_length(self):
        """Test that code verifier has appropriate length (43-128 chars)."""
        pkce = generate_pkce_params()

        # Base64url encoding of 32 bytes gives ~43 chars
        assert len(pkce.code_verifier) >= 43
        assert len(pkce.code_verifier) <= 128

    def test_code_verifier_characters(self):
        """Test that code verifier uses only allowed characters."""
        # RFC 7636: unreserved characters [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

        for _ in range(10):  # Test multiple generations
            pkce = generate_pkce_params()
            for char in pkce.code_verifier:
                assert char in allowed, f"Invalid character '{char}' in code_verifier"

    def test_code_challenge_is_sha256_of_verifier(self):
        """Test that code challenge is correctly derived from verifier."""
        pkce = generate_pkce_params()

        # Manually compute expected challenge
        digest = hashlib.sha256(pkce.code_verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        assert pkce.code_challenge == expected

    def test_code_challenge_no_padding(self):
        """Test that code challenge has no base64 padding."""
        pkce = generate_pkce_params()

        assert "=" not in pkce.code_challenge

    def test_multiple_generations_are_unique(self):
        """Test that each generation produces unique values."""
        verifiers = set()
        challenges = set()

        for _ in range(100):
            pkce = generate_pkce_params()
            verifiers.add(pkce.code_verifier)
            challenges.add(pkce.code_challenge)

        # All should be unique
        assert len(verifiers) == 100
        assert len(challenges) == 100


class TestCredentials:
    """Test Credentials dataclass."""

    def test_credentials_creation(self):
        """Test creating a Credentials object."""
        creds = Credentials(
            access_token="test_access",
            refresh_token="test_refresh",
            expires_at=time.time() + 3600,
            token_type="Bearer",
            user_info={"email": "test@example.com"},
        )

        assert creds.access_token == "test_access"
        assert creds.refresh_token == "test_refresh"
        assert creds.token_type == "Bearer"
        assert creds.user_info["email"] == "test@example.com"

    def test_is_expired_false_for_future_expiry(self):
        """Test that is_expired returns False for non-expired tokens."""
        creds = Credentials(
            access_token="test",
            refresh_token=None,
            expires_at=time.time() + 3600,  # 1 hour from now
            token_type="Bearer",
        )

        assert creds.is_expired() is False

    def test_is_expired_true_for_past_expiry(self):
        """Test that is_expired returns True for expired tokens."""
        creds = Credentials(
            access_token="test",
            refresh_token=None,
            expires_at=time.time() - 100,  # 100 seconds ago
            token_type="Bearer",
        )

        assert creds.is_expired() is True

    def test_is_expired_with_buffer(self):
        """Test that is_expired considers buffer time."""
        # Token expires in 30 seconds
        creds = Credentials(
            access_token="test",
            refresh_token=None,
            expires_at=time.time() + 30,
            token_type="Bearer",
        )

        # With 60 second buffer, should be considered expired
        assert creds.is_expired(buffer_seconds=60) is True

        # With 10 second buffer, should not be expired
        assert creds.is_expired(buffer_seconds=10) is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        expires_at = time.time() + 3600
        creds = Credentials(
            access_token="test_access",
            refresh_token="test_refresh",
            expires_at=expires_at,
            token_type="Bearer",
            user_info={"email": "test@example.com"},
        )

        d = creds.to_dict()

        assert d["access_token"] == "test_access"
        assert d["refresh_token"] == "test_refresh"
        assert d["expires_at"] == expires_at
        assert d["token_type"] == "Bearer"
        assert d["user_info"]["email"] == "test@example.com"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        expires_at = time.time() + 3600
        d = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "expires_at": expires_at,
            "token_type": "Bearer",
            "user_info": {"email": "test@example.com"},
        }

        creds = Credentials.from_dict(d)

        assert creds.access_token == "test_access"
        assert creds.refresh_token == "test_refresh"
        assert creds.expires_at == expires_at
        assert creds.token_type == "Bearer"
        assert creds.user_info["email"] == "test@example.com"

    def test_from_dict_with_missing_optional_fields(self):
        """Test deserialization handles missing optional fields."""
        d = {
            "access_token": "test_access",
            "expires_at": time.time() + 3600,
        }

        creds = Credentials.from_dict(d)

        assert creds.access_token == "test_access"
        assert creds.refresh_token is None
        assert creds.token_type == "Bearer"  # Default value
        assert creds.user_info is None


class TestTokenStorage:
    """Test token storage and loading."""

    @pytest.fixture
    def temp_credentials_dir(self, tmp_path, monkeypatch):
        """Set up temporary credentials directory."""
        creds_dir = tmp_path / ".voicemode"
        creds_file = creds_dir / "credentials"

        # Patch the module-level constants
        monkeypatch.setattr("voice_mode.auth.CREDENTIALS_DIR", creds_dir)
        monkeypatch.setattr("voice_mode.auth.CREDENTIALS_FILE", creds_file)

        return creds_dir, creds_file

    def test_save_credentials_creates_directory(self, temp_credentials_dir):
        """Test that save_credentials creates the directory if needed."""
        creds_dir, creds_file = temp_credentials_dir

        assert not creds_dir.exists()

        creds = Credentials(
            access_token="test",
            refresh_token=None,
            expires_at=time.time() + 3600,
            token_type="Bearer",
        )

        save_credentials(creds)

        assert creds_dir.exists()
        assert creds_file.exists()

    def test_save_credentials_sets_permissions(self, temp_credentials_dir):
        """Test that save_credentials sets 0600 permissions."""
        creds_dir, creds_file = temp_credentials_dir

        creds = Credentials(
            access_token="test",
            refresh_token=None,
            expires_at=time.time() + 3600,
            token_type="Bearer",
        )

        save_credentials(creds)

        # Check file permissions (octal 0o600 = user read/write only)
        mode = os.stat(creds_file).st_mode & 0o777
        assert mode == 0o600

    def test_save_and_load_credentials(self, temp_credentials_dir):
        """Test round-trip save and load."""
        expires_at = time.time() + 3600
        creds = Credentials(
            access_token="test_access",
            refresh_token="test_refresh",
            expires_at=expires_at,
            token_type="Bearer",
            user_info={"email": "test@example.com"},
        )

        save_credentials(creds)
        loaded = load_credentials()

        assert loaded is not None
        assert loaded.access_token == "test_access"
        assert loaded.refresh_token == "test_refresh"
        assert loaded.expires_at == expires_at
        assert loaded.token_type == "Bearer"
        assert loaded.user_info["email"] == "test@example.com"

    def test_load_credentials_returns_none_when_missing(self, temp_credentials_dir):
        """Test that load_credentials returns None when file doesn't exist."""
        loaded = load_credentials()
        assert loaded is None

    def test_load_credentials_returns_none_for_invalid_json(self, temp_credentials_dir):
        """Test that load_credentials handles corrupt files gracefully."""
        creds_dir, creds_file = temp_credentials_dir
        creds_dir.mkdir(parents=True)

        creds_file.write_text("not valid json {{{")

        loaded = load_credentials()
        assert loaded is None

    def test_load_credentials_returns_none_for_missing_fields(self, temp_credentials_dir):
        """Test that load_credentials handles incomplete data."""
        creds_dir, creds_file = temp_credentials_dir
        creds_dir.mkdir(parents=True)

        creds_file.write_text('{"only_one_field": "value"}')

        loaded = load_credentials()
        assert loaded is None

    def test_clear_credentials(self, temp_credentials_dir):
        """Test clearing credentials."""
        creds_dir, creds_file = temp_credentials_dir

        creds = Credentials(
            access_token="test",
            refresh_token=None,
            expires_at=time.time() + 3600,
            token_type="Bearer",
        )

        save_credentials(creds)
        assert creds_file.exists()

        result = clear_credentials()

        assert result is True
        assert not creds_file.exists()

    def test_clear_credentials_returns_false_when_missing(self, temp_credentials_dir):
        """Test that clear_credentials returns False when file doesn't exist."""
        result = clear_credentials()
        assert result is False


class TestPortSelection:
    """Test port selection for callback server."""

    def test_find_available_port_returns_port_in_range(self):
        """Test that find_available_port returns a port in the valid range."""
        port = find_available_port()

        # Should get a port (unless all are busy, which is unlikely in tests)
        assert port is None or CALLBACK_PORT_START <= port <= CALLBACK_PORT_END

    def test_find_available_port_with_busy_port(self):
        """Test fallback when primary port is busy."""
        # Try to occupy the first port by binding AND listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(("127.0.0.1", CALLBACK_PORT_START))
            sock.listen(1)  # Must listen to truly occupy the port
        except OSError:
            sock.close()
            pytest.skip(f"Port {CALLBACK_PORT_START} already in use, cannot run test")
            return

        try:
            # Should get a different port
            port = find_available_port()

            # Either None (all busy) or a fallback port
            assert port is None or port != CALLBACK_PORT_START
            if port is not None:
                assert CALLBACK_PORT_START < port <= CALLBACK_PORT_END
        finally:
            sock.close()

    def test_find_available_port_returns_none_when_all_busy(self):
        """Test that find_available_port returns None when all ports are busy."""
        # Occupy all ports in range by binding AND listening
        sockets = []
        try:
            for port in range(CALLBACK_PORT_START, CALLBACK_PORT_END + 1):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", port))
                    sock.listen(1)  # Must listen to truly occupy the port
                    sockets.append(sock)
                except OSError:
                    sock.close()
                    # Port already in use, clean up and skip test
                    for s in sockets:
                        s.close()
                    pytest.skip(f"Port {port} already in use, cannot run test")
                    return

            result = find_available_port()
            assert result is None

        finally:
            for sock in sockets:
                sock.close()


class TestCallbackServer:
    """Test the OAuth callback server."""

    def test_server_starts_and_stops(self):
        """Test that server can start and stop."""
        port = find_available_port()
        if port is None:
            pytest.skip("No available port for test")

        server = CallbackServer(port)
        server.start()

        # Server should be running
        assert server.server is not None
        assert server.thread is not None
        assert server.thread.is_alive()

        server.stop()

        # Give it a moment to stop
        time.sleep(0.1)

    def test_redirect_uri(self):
        """Test redirect_uri property."""
        server = CallbackServer(8765)
        assert server.redirect_uri == "http://localhost:8765/callback"

    def test_wait_for_callback_timeout(self):
        """Test that wait_for_callback returns None on timeout."""
        port = find_available_port()
        if port is None:
            pytest.skip("No available port for test")

        server = CallbackServer(port)
        server.start()

        try:
            # Very short timeout
            result = server.wait_for_callback(timeout=0.1)
            assert result is None
        finally:
            server.stop()


class TestBuildAuthorizeUrl:
    """Test authorization URL building."""

    def test_build_authorize_url_basic(self):
        """Test basic URL construction."""
        pkce = PKCEParams(
            code_verifier="test_verifier",
            code_challenge="test_challenge",
        )

        url = build_authorize_url("http://localhost:8765/callback", pkce)

        assert f"https://{AUTH0_DOMAIN}/authorize" in url
        assert "response_type=code" in url
        assert f"client_id={AUTH0_CLIENT_ID}" in url
        assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback" in url
        assert "code_challenge=test_challenge" in url
        assert "code_challenge_method=S256" in url

    def test_build_authorize_url_with_state(self):
        """Test URL with state parameter."""
        pkce = PKCEParams(
            code_verifier="test_verifier",
            code_challenge="test_challenge",
        )

        url = build_authorize_url("http://localhost:8765/callback", pkce, state="test_state")

        assert "state=test_state" in url


class TestTokenExchange:
    """Test token exchange with Auth0 (mocked)."""

    def test_exchange_code_for_tokens_success(self):
        """Test successful token exchange."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = exchange_code_for_tokens(
                code="auth_code",
                code_verifier="verifier",
                redirect_uri="http://localhost:8765/callback",
            )

            assert result["access_token"] == "new_access_token"
            assert result["refresh_token"] == "new_refresh_token"

    def test_exchange_code_for_tokens_error(self):
        """Test token exchange failure."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Invalid authorization code",
        }

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            with pytest.raises(AuthError) as exc_info:
                exchange_code_for_tokens(
                    code="bad_code",
                    code_verifier="verifier",
                    redirect_uri="http://localhost:8765/callback",
                )

            assert "invalid_grant" in str(exc_info.value)


class TestTokenRefresh:
    """Test token refresh (mocked)."""

    def test_refresh_access_token_success(self):
        """Test successful token refresh."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed_access_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = refresh_access_token("old_refresh_token")

            assert result["access_token"] == "refreshed_access_token"

    def test_refresh_access_token_error(self):
        """Test refresh failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Refresh token expired",
        }

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            with pytest.raises(AuthError) as exc_info:
                refresh_access_token("expired_refresh_token")

            assert "invalid_grant" in str(exc_info.value)


class TestGetUserInfo:
    """Test user info fetching (mocked)."""

    def test_get_user_info_success(self):
        """Test successful user info fetch."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "sub": "auth0|123",
            "email": "test@example.com",
            "name": "Test User",
        }

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            result = get_user_info("valid_token")

            assert result["email"] == "test@example.com"
            assert result["name"] == "Test User"

    def test_get_user_info_error(self):
        """Test user info fetch failure."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_response

            with pytest.raises(AuthError) as exc_info:
                get_user_info("invalid_token")

            assert "Failed to fetch user info" in str(exc_info.value)


class TestGetValidCredentials:
    """Test get_valid_credentials with auto-refresh."""

    @pytest.fixture
    def temp_credentials_dir(self, tmp_path, monkeypatch):
        """Set up temporary credentials directory."""
        creds_dir = tmp_path / ".voicemode"
        creds_file = creds_dir / "credentials"

        monkeypatch.setattr("voice_mode.auth.CREDENTIALS_DIR", creds_dir)
        monkeypatch.setattr("voice_mode.auth.CREDENTIALS_FILE", creds_file)

        return creds_dir, creds_file

    def test_returns_none_when_not_logged_in(self, temp_credentials_dir):
        """Test returns None when no credentials exist."""
        result = get_valid_credentials()
        assert result is None

    def test_returns_credentials_when_not_expired(self, temp_credentials_dir):
        """Test returns credentials directly when not expired."""
        creds = Credentials(
            access_token="valid_token",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
            token_type="Bearer",
        )
        save_credentials(creds)

        result = get_valid_credentials()

        assert result is not None
        assert result.access_token == "valid_token"

    def test_refreshes_expired_credentials(self, temp_credentials_dir):
        """Test auto-refresh of expired credentials."""
        creds = Credentials(
            access_token="expired_token",
            refresh_token="valid_refresh",
            expires_at=time.time() - 100,  # Expired
            token_type="Bearer",
        )
        save_credentials(creds)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with patch("voice_mode.auth.httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response

            result = get_valid_credentials(auto_refresh=True)

            assert result is not None
            assert result.access_token == "new_token"

    def test_returns_none_when_refresh_disabled(self, temp_credentials_dir):
        """Test returns None for expired credentials when auto_refresh=False."""
        creds = Credentials(
            access_token="expired_token",
            refresh_token="valid_refresh",
            expires_at=time.time() - 100,  # Expired
            token_type="Bearer",
        )
        save_credentials(creds)

        result = get_valid_credentials(auto_refresh=False)

        assert result is None


class TestFormatExpiry:
    """Test expiry time formatting."""

    def test_format_expiry_expired(self):
        """Test formatting expired time."""
        result = format_expiry(time.time() - 100)
        assert result == "expired"

    def test_format_expiry_minutes(self):
        """Test formatting time in minutes."""
        result = format_expiry(time.time() + 180)  # 3 minutes
        assert "minute" in result

    def test_format_expiry_hours(self):
        """Test formatting time in hours."""
        result = format_expiry(time.time() + 7200)  # 2 hours
        assert "h" in result

    def test_format_expiry_days(self):
        """Test formatting time in days."""
        result = format_expiry(time.time() + 86400 * 2)  # 2 days
        assert "day" in result


class TestLoginCLI:
    """Test the 'voicemode connect login' CLI command."""

    def test_login_command_exists(self):
        """Test that login command is registered under connect group."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()
        result = runner.invoke(connect, ["login", "--help"])

        assert result.exit_code == 0
        assert "Authenticate with voicemode.dev" in result.output
        assert "--no-browser" in result.output

    def test_login_success(self):
        """Test successful login flow."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        mock_credentials = Credentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=time.time() + 3600,
            token_type="Bearer",
            user_info={"email": "test@example.com", "name": "Test User"},
        )

        runner = CliRunner()

        with patch("voice_mode.auth.login", return_value=mock_credentials) as mock_login:
            result = runner.invoke(connect, ["login", "--no-browser"])

            # Should have called auth.login
            assert mock_login.called
            call_kwargs = mock_login.call_args[1]
            assert call_kwargs["open_browser"] is False

            # Should show success output
            assert result.exit_code == 0
            assert "Authentication successful" in result.output
            assert "Test User" in result.output
            assert "test@example.com" in result.output

    def test_login_cancelled(self):
        """Test login cancelled by user (Ctrl+C)."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()

        with patch("voice_mode.auth.login", side_effect=KeyboardInterrupt()):
            result = runner.invoke(connect, ["login", "--no-browser"])

            assert result.exit_code == 1
            assert "cancelled" in result.output.lower()

    def test_login_timeout(self):
        """Test login timeout."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()

        with patch("voice_mode.auth.login", side_effect=AuthError("Authentication timed out. Please try again.")):
            result = runner.invoke(connect, ["login", "--no-browser"])

            assert result.exit_code == 1
            assert "timed out" in result.output.lower()

    def test_login_auth_error(self):
        """Test login with auth error."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()

        with patch("voice_mode.auth.login", side_effect=AuthError("No available ports")):
            result = runner.invoke(connect, ["login", "--no-browser"])

            assert result.exit_code == 1
            assert "failed" in result.output.lower()
            assert "No available ports" in result.output

    def test_login_no_browser_shows_url(self):
        """Test --no-browser option shows URL in output."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        mock_credentials = Credentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=time.time() + 3600,
            token_type="Bearer",
            user_info=None,
        )

        runner = CliRunner()

        def mock_login(open_browser, on_browser_open, on_waiting):
            # Simulate callback with URL
            if on_browser_open:
                on_browser_open("https://auth0.test/authorize?foo=bar")
            if on_waiting:
                on_waiting()
            return mock_credentials

        with patch("voice_mode.auth.login", side_effect=mock_login):
            result = runner.invoke(connect, ["login", "--no-browser"])

            assert result.exit_code == 0
            # When --no-browser is set, URL should be displayed
            assert "https://auth0.test/authorize" in result.output
            assert "Open this URL" in result.output


class TestLogoutCLI:
    """Test the 'voicemode connect logout' CLI command."""

    def test_logout_command_exists(self):
        """Test that logout command is registered under connect group."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()
        result = runner.invoke(connect, ["logout", "--help"])

        assert result.exit_code == 0
        assert "Log out from voicemode.dev" in result.output

    def test_logout_with_credentials(self):
        """Test logout when credentials exist."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        mock_credentials = Credentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=time.time() + 3600,
            token_type="Bearer",
            user_info={"email": "test@example.com", "name": "Test User"},
        )

        runner = CliRunner()

        with patch("voice_mode.auth.load_credentials", return_value=mock_credentials), \
             patch("voice_mode.auth.clear_credentials", return_value=True):
            result = runner.invoke(connect, ["logout"])

            assert result.exit_code == 0
            assert "Logged out successfully" in result.output
            assert "test@example.com" in result.output

    def test_logout_no_credentials(self):
        """Test logout when no credentials stored."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()

        with patch("voice_mode.auth.load_credentials", return_value=None), \
             patch("voice_mode.auth.clear_credentials", return_value=False):
            result = runner.invoke(connect, ["logout"])

            assert result.exit_code == 0
            assert "Already logged out" in result.output

    def test_logout_credentials_without_email(self):
        """Test logout with credentials that have no email in user_info."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        mock_credentials = Credentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=time.time() + 3600,
            token_type="Bearer",
            user_info={},  # No email
        )

        runner = CliRunner()

        with patch("voice_mode.auth.load_credentials", return_value=mock_credentials), \
             patch("voice_mode.auth.clear_credentials", return_value=True):
            result = runner.invoke(connect, ["logout"])

            assert result.exit_code == 0
            assert "Logged out successfully" in result.output
            # Should not show "Removed credentials for:" since no email
            assert "Removed credentials for:" not in result.output
