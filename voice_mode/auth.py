"""
OAuth authentication module for VoiceMode CLI.

Implements PKCE flow for secure authentication with voicemode.dev via Auth0.
Handles token storage, loading, refresh, and expiry management.

Storage: ~/.voicemode/credentials (JSON, mode 0600)
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx


# Auth0 configuration
AUTH0_DOMAIN = "dev-2q681p5hobd1dtmm.us.auth0.com"
AUTH0_CLIENT_ID = "voicemode-cli"  # Public client ID for native app
AUTH0_SCOPES = "openid profile email offline_access"
AUTH0_AUDIENCE = "https://voicemode.dev/api"

# Port range for localhost callback server
CALLBACK_PORT_START = 8765
CALLBACK_PORT_END = 8769
CALLBACK_TIMEOUT_SECONDS = 300  # 5 minutes

# Credentials file path
CREDENTIALS_DIR = Path.home() / ".voicemode"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials"


@dataclass
class Credentials:
    """Stored OAuth credentials."""

    access_token: str
    refresh_token: str | None
    expires_at: float  # Unix timestamp
    token_type: str
    user_info: dict | None = None

    def is_expired(self, buffer_seconds: int = 60) -> bool:
        """Check if access token is expired or will expire soon."""
        return time.time() >= (self.expires_at - buffer_seconds)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "user_info": self.user_info,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Credentials":
        """Create from dictionary."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=data["expires_at"],
            token_type=data.get("token_type", "Bearer"),
            user_info=data.get("user_info"),
        )


@dataclass
class PKCEParams:
    """PKCE parameters for OAuth flow."""

    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"


def generate_pkce_params() -> PKCEParams:
    """
    Generate PKCE code verifier and challenge.

    The code verifier is a cryptographically random string using characters
    [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~" with a minimum length of
    43 characters and maximum of 128 characters.

    The code challenge is the Base64-URL-encoded SHA256 hash of the verifier.
    """
    # Generate 32 random bytes, base64url encode to get ~43 chars
    code_verifier = secrets.token_urlsafe(32)

    # SHA256 hash the verifier
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()

    # Base64url encode without padding
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    return PKCEParams(code_verifier=code_verifier, code_challenge=code_challenge)


def find_available_port(start: int = CALLBACK_PORT_START, end: int = CALLBACK_PORT_END) -> int | None:
    """
    Find an available port in the given range.

    Returns the first available port, or None if all ports are busy.
    """
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""

    # These will be set by the CallbackServer
    callback_result: dict | None = None
    callback_event: threading.Event | None = None

    def log_message(self, format: str, *args) -> None:
        """Suppress HTTP server logs."""
        pass

    def do_GET(self) -> None:
        """Handle GET request from OAuth callback."""
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        # Parse query parameters
        params = urllib.parse.parse_qs(parsed.query)

        # Check for error
        if "error" in params:
            error = params.get("error", ["unknown"])[0]
            error_desc = params.get("error_description", ["No description"])[0]
            CallbackHandler.callback_result = {"error": error, "error_description": error_desc}
        elif "code" in params:
            code = params["code"][0]
            state = params.get("state", [None])[0]
            CallbackHandler.callback_result = {"code": code, "state": state}
        else:
            CallbackHandler.callback_result = {"error": "invalid_response", "error_description": "Missing authorization code"}

        # Send response to browser
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if "error" in CallbackHandler.callback_result:
            html = """
            <html><body style="font-family: system-ui; text-align: center; padding: 50px;">
            <h1>Authentication Failed</h1>
            <p>Error: {}</p>
            <p>You can close this window.</p>
            </body></html>
            """.format(
                CallbackHandler.callback_result.get("error_description", "Unknown error")
            )
        else:
            html = """
            <html><body style="font-family: system-ui; text-align: center; padding: 50px;">
            <h1>Authentication Successful!</h1>
            <p>You can close this window and return to the terminal.</p>
            </body></html>
            """

        self.wfile.write(html.encode("utf-8"))

        # Signal that we received the callback
        if CallbackHandler.callback_event:
            CallbackHandler.callback_event.set()


class CallbackServer:
    """HTTP server for receiving OAuth callback."""

    def __init__(self, port: int):
        self.port = port
        self.server: http.server.HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.event = threading.Event()
        self._shutdown = False

        # Reset class-level state
        CallbackHandler.callback_result = None
        CallbackHandler.callback_event = self.event

    @property
    def redirect_uri(self) -> str:
        """Get the redirect URI for this server."""
        return f"http://localhost:{self.port}/callback"

    def start(self) -> None:
        """Start the callback server in a background thread."""
        self.server = http.server.HTTPServer(("127.0.0.1", self.port), CallbackHandler)
        self.server.timeout = 0.5  # Short timeout for checking shutdown flag

        def serve():
            while not self._shutdown:
                self.server.handle_request()

        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()

    def wait_for_callback(self, timeout: float = CALLBACK_TIMEOUT_SECONDS) -> dict | None:
        """Wait for the OAuth callback."""
        if self.event.wait(timeout=timeout):
            return CallbackHandler.callback_result
        return None  # Timeout

    def stop(self) -> None:
        """Stop the callback server."""
        self._shutdown = True
        self.event.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.server:
            self.server.server_close()


def exchange_code_for_tokens(
    code: str,
    code_verifier: str,
    redirect_uri: str,
    timeout: float = 30.0,
) -> dict:
    """
    Exchange authorization code for tokens.

    Args:
        code: Authorization code from OAuth callback
        code_verifier: PKCE code verifier
        redirect_uri: The redirect URI used in the authorization request
        timeout: HTTP request timeout in seconds

    Returns:
        Token response containing access_token, refresh_token, etc.

    Raises:
        AuthError: If token exchange fails
    """
    token_url = f"https://{AUTH0_DOMAIN}/oauth/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": AUTH0_CLIENT_ID,
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            try:
                error_data = response.json()
                error = error_data.get("error", "unknown")
                desc = error_data.get("error_description", "Token exchange failed")
            except Exception:
                error = "http_error"
                desc = f"HTTP {response.status_code}: {response.text}"
            raise AuthError(f"{error}: {desc}")

        return response.json()


def refresh_access_token(refresh_token: str, timeout: float = 30.0) -> dict:
    """
    Refresh an access token using a refresh token.

    Args:
        refresh_token: The refresh token
        timeout: HTTP request timeout in seconds

    Returns:
        Token response with new access_token (and possibly new refresh_token)

    Raises:
        AuthError: If refresh fails
    """
    token_url = f"https://{AUTH0_DOMAIN}/oauth/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": AUTH0_CLIENT_ID,
        "refresh_token": refresh_token,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            try:
                error_data = response.json()
                error = error_data.get("error", "unknown")
                desc = error_data.get("error_description", "Token refresh failed")
            except Exception:
                error = "http_error"
                desc = f"HTTP {response.status_code}: {response.text}"
            raise AuthError(f"{error}: {desc}")

        return response.json()


def get_user_info(access_token: str, timeout: float = 30.0) -> dict:
    """
    Fetch user info from Auth0 userinfo endpoint.

    Args:
        access_token: Valid access token
        timeout: HTTP request timeout in seconds

    Returns:
        User info dictionary

    Raises:
        AuthError: If request fails
    """
    userinfo_url = f"https://{AUTH0_DOMAIN}/userinfo"

    with httpx.Client(timeout=timeout) as client:
        response = client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            raise AuthError(f"Failed to fetch user info: HTTP {response.status_code}")

        return response.json()


class AuthError(Exception):
    """Authentication error."""

    pass


def save_credentials(credentials: Credentials) -> None:
    """
    Save credentials to disk.

    Creates the credentials directory if needed and sets file permissions to 0600.

    Args:
        credentials: Credentials to save
    """
    # Ensure directory exists
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    # Write credentials
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(credentials.to_dict(), f, indent=2)

    # Set restrictive permissions (user read/write only)
    os.chmod(CREDENTIALS_FILE, 0o600)


def load_credentials() -> Credentials | None:
    """
    Load credentials from disk.

    Returns:
        Credentials if file exists and is valid, None otherwise
    """
    if not CREDENTIALS_FILE.exists():
        return None

    try:
        with open(CREDENTIALS_FILE) as f:
            data = json.load(f)
        return Credentials.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def clear_credentials() -> bool:
    """
    Delete stored credentials.

    Returns:
        True if credentials were deleted, False if they didn't exist
    """
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        return True
    return False


def get_valid_credentials(auto_refresh: bool = True) -> Credentials | None:
    """
    Get valid (non-expired) credentials, optionally refreshing if needed.

    Args:
        auto_refresh: If True, attempt to refresh expired credentials

    Returns:
        Valid credentials, or None if not logged in or refresh failed
    """
    credentials = load_credentials()
    if credentials is None:
        return None

    if not credentials.is_expired():
        return credentials

    if not auto_refresh or not credentials.refresh_token:
        return None

    try:
        token_response = refresh_access_token(credentials.refresh_token)

        # Calculate new expiry time
        expires_in = token_response.get("expires_in", 3600)
        expires_at = time.time() + expires_in

        # Update credentials (may get new refresh token too)
        credentials = Credentials(
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token", credentials.refresh_token),
            expires_at=expires_at,
            token_type=token_response.get("token_type", "Bearer"),
            user_info=credentials.user_info,
        )

        save_credentials(credentials)
        return credentials

    except AuthError:
        return None


def build_authorize_url(redirect_uri: str, pkce: PKCEParams, state: str | None = None) -> str:
    """
    Build the Auth0 authorization URL.

    Args:
        redirect_uri: OAuth callback URI
        pkce: PKCE parameters
        state: Optional state parameter for CSRF protection

    Returns:
        Authorization URL to open in browser
    """
    params = {
        "response_type": "code",
        "client_id": AUTH0_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": AUTH0_SCOPES,
        "audience": AUTH0_AUDIENCE,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": pkce.code_challenge_method,
    }

    if state:
        params["state"] = state

    query = urllib.parse.urlencode(params)
    return f"https://{AUTH0_DOMAIN}/authorize?{query}"


def login(
    open_browser: bool = True,
    on_browser_open: Callable[[str], None] | None = None,
    on_waiting: Callable[[], None] | None = None,
) -> Credentials:
    """
    Perform OAuth login flow.

    Starts a local HTTP server, opens browser to Auth0, waits for callback,
    exchanges code for tokens, fetches user info, and saves credentials.

    Args:
        open_browser: Whether to automatically open browser
        on_browser_open: Callback when browser should be opened (receives URL)
        on_waiting: Callback while waiting for user to complete auth

    Returns:
        Credentials after successful login

    Raises:
        AuthError: If login fails
    """
    # Find available port
    port = find_available_port()
    if port is None:
        raise AuthError(
            f"No available ports in range {CALLBACK_PORT_START}-{CALLBACK_PORT_END}. "
            "Please close applications using these ports and try again."
        )

    # Generate PKCE parameters
    pkce = generate_pkce_params()

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(16)

    # Start callback server
    server = CallbackServer(port)
    server.start()

    try:
        # Build authorization URL
        auth_url = build_authorize_url(server.redirect_uri, pkce, state)

        # Open browser
        if on_browser_open:
            on_browser_open(auth_url)
        if open_browser:
            webbrowser.open(auth_url)

        # Wait for callback
        if on_waiting:
            on_waiting()

        result = server.wait_for_callback()

        if result is None:
            raise AuthError("Authentication timed out. Please try again.")

        if "error" in result:
            raise AuthError(f"{result['error']}: {result.get('error_description', 'Unknown error')}")

        # Verify state
        if result.get("state") != state:
            raise AuthError("State mismatch - possible CSRF attack. Please try again.")

        code = result["code"]

        # Exchange code for tokens
        token_response = exchange_code_for_tokens(
            code=code,
            code_verifier=pkce.code_verifier,
            redirect_uri=server.redirect_uri,
        )

        # Calculate expiry time
        expires_in = token_response.get("expires_in", 3600)
        expires_at = time.time() + expires_in

        # Get user info
        user_info = None
        try:
            user_info = get_user_info(token_response["access_token"])
        except AuthError:
            pass  # User info is optional

        # Create credentials
        credentials = Credentials(
            access_token=token_response["access_token"],
            refresh_token=token_response.get("refresh_token"),
            expires_at=expires_at,
            token_type=token_response.get("token_type", "Bearer"),
            user_info=user_info,
        )

        # Save credentials
        save_credentials(credentials)

        return credentials

    finally:
        server.stop()


def format_expiry(expires_at: float) -> str:
    """Format expiry timestamp as human-readable string."""
    dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    if dt <= now:
        return "expired"

    delta = dt - now
    if delta.days > 0:
        return f"in {delta.days} day{'s' if delta.days != 1 else ''}"
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if hours > 0:
        return f"in {hours}h {minutes}m"
    if minutes > 0:
        return f"in {minutes} minute{'s' if minutes != 1 else ''}"
    return f"in {delta.seconds} second{'s' if delta.seconds != 1 else ''}"
