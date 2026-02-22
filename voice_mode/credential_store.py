"""
Credential storage backends for VoiceMode.

Provides KeyringStore (OS keychain) and PlaintextStore (file-based) implementations.
The active store is selected based on VOICEMODE_CREDENTIAL_STORE environment variable
and keyring backend availability.

Default: plaintext (file-based)
Opt-in: VOICEMODE_CREDENTIAL_STORE=keyring
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger("voicemode")

# Service name for keyring storage
KEYRING_SERVICE = "voicemode"
KEYRING_USERNAME = "credentials"

# Plaintext storage paths
CREDENTIALS_DIR = Path.home() / ".voicemode"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials"
CREDENTIALS_MIGRATED_FILE = CREDENTIALS_DIR / "credentials.migrated"


class CredentialStore(ABC):
    """Abstract base class for credential storage."""

    @abstractmethod
    def save(self, data: dict) -> None:
        """Save credentials data."""

    @abstractmethod
    def load(self) -> dict | None:
        """Load credentials data. Returns None if not found."""

    @abstractmethod
    def clear(self) -> bool:
        """Clear stored credentials. Returns True if credentials existed."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the store backend."""


class KeyringStore(CredentialStore):
    """Store credentials in the OS keychain via the keyring library."""

    def save(self, data: dict) -> None:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, json.dumps(data))

    def load(self) -> dict | None:
        import keyring

        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def clear(self) -> bool:
        import keyring

        existing = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if existing is None:
            return False
        try:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
            return True
        except keyring.errors.PasswordDeleteError:
            return False

    @property
    def name(self) -> str:
        return "keyring"


class PlaintextStore(CredentialStore):
    """Store credentials as JSON on disk with restrictive permissions."""

    def save(self, data: dict) -> None:
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(CREDENTIALS_FILE, 0o600)

    def load(self) -> dict | None:
        if not CREDENTIALS_FILE.exists():
            return None
        try:
            with open(CREDENTIALS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def clear(self) -> bool:
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
            return True
        return False

    @property
    def name(self) -> str:
        return "plaintext"


def _keyring_backend_is_viable() -> bool:
    """Check if the keyring backend can actually store secrets.

    Returns False if the backend is the fail.Keyring or chainer.ChainerBackend
    with no viable backends (common on headless Linux), or if the keychain is
    inaccessible at runtime (e.g. macOS over SSH, error -25308).
    """
    try:
        import keyring

        backend = keyring.get_keyring()
        backend_name = type(backend).__module__ + "." + type(backend).__qualname__

        # Known non-functional backends
        fail_backends = {
            "keyring.backends.fail.Keyring",
            "keyrings.alt.file.PlaintextKeyring",
        }
        if backend_name in fail_backends:
            return False

        # ChainerBackend wraps multiple backends; check if any are viable
        if hasattr(backend, "backends"):
            viable = [
                b
                for b in backend.backends
                if (type(b).__module__ + "." + type(b).__qualname__) not in fail_backends
            ]
            if len(viable) == 0:
                return False

        # Probe actual keychain access — catches macOS Keychain errors
        # over SSH (error -25308) and similar runtime failures
        try:
            keyring.get_password(KEYRING_SERVICE, "__voicemode_probe__")
        except Exception:
            return False

        return True
    except Exception:
        return False


def _migrate_plaintext_to_keyring(keyring_store: KeyringStore) -> None:
    """Migrate existing plaintext credentials to the keyring.

    If ~/.voicemode/credentials exists and keyring has no stored credentials:
    1. Read from plaintext
    2. Store in keyring
    3. Rename plaintext file to credentials.migrated
    """
    if not CREDENTIALS_FILE.exists():
        return

    # Only migrate if keyring is empty
    if keyring_store.load() is not None:
        return

    plaintext = PlaintextStore()
    data = plaintext.load()
    if data is None:
        return

    try:
        keyring_store.save(data)
        CREDENTIALS_FILE.rename(CREDENTIALS_MIGRATED_FILE)
        logger.info("Credentials migrated to OS keychain")
    except Exception as e:
        logger.warning(f"Failed to migrate credentials to keyring: {e}")


_cached_store: CredentialStore | None = None


def get_credential_store() -> CredentialStore:
    """Get the active credential store based on configuration and availability.

    Priority:
    1. VOICEMODE_CREDENTIAL_STORE=plaintext (or unset, default) -> PlaintextStore
    2. VOICEMODE_CREDENTIAL_STORE=keyring -> KeyringStore if viable
    3. Fallback to PlaintextStore with warning if keyring backend is unavailable
    """
    global _cached_store
    if _cached_store is not None:
        return _cached_store

    store_type = os.getenv("VOICEMODE_CREDENTIAL_STORE", "plaintext").lower()

    if store_type == "plaintext":
        _cached_store = PlaintextStore()
        return _cached_store

    # Explicit keyring request
    if store_type == "keyring" and _keyring_backend_is_viable():
        store = KeyringStore()
        _migrate_plaintext_to_keyring(store)
        _cached_store = store
        return _cached_store

    # Keyring requested but not viable — fall back
    if store_type == "keyring":
        logger.warning(
            "Keyring backend unavailable (headless system?). "
            "Falling back to plaintext credential storage. "
            "Set VOICEMODE_CREDENTIAL_STORE=plaintext to suppress this warning."
        )

    _cached_store = PlaintextStore()
    return _cached_store
