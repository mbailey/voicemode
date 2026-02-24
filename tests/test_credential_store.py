"""
Unit tests for voice_mode.credential_store module.

Tests KeyringStore, PlaintextStore, migration, and fallback behavior.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import voice_mode.credential_store as cred_mod
from voice_mode.credential_store import (
    KEYRING_SERVICE,
    KEYRING_USERNAME,
    KeyringStore,
    PlaintextStore,
    get_credential_store,
    _keyring_backend_is_viable,
    _migrate_plaintext_to_keyring,
)


SAMPLE_CREDENTIALS = {
    "access_token": "test-access-token",
    "refresh_token": "test-refresh-token",
    "expires_at": 9999999999.0,
    "token_type": "Bearer",
    "user_info": {"email": "test@example.com"},
}


# ──────────────────────────────────────────────────────────────────
# PlaintextStore tests
# ──────────────────────────────────────────────────────────────────


class TestPlaintextStore:
    """Tests for the PlaintextStore backend."""

    @pytest.fixture(autouse=True)
    def temp_credentials_dir(self, tmp_path, monkeypatch):
        """Redirect credential paths to a temp directory."""
        cred_dir = tmp_path / ".voicemode"
        cred_file = cred_dir / "credentials"
        migrated_file = cred_dir / "credentials.migrated"
        monkeypatch.setattr("voice_mode.credential_store.CREDENTIALS_DIR", cred_dir)
        monkeypatch.setattr("voice_mode.credential_store.CREDENTIALS_FILE", cred_file)
        monkeypatch.setattr("voice_mode.credential_store.CREDENTIALS_MIGRATED_FILE", migrated_file)
        return cred_dir

    def test_save_creates_directory(self, temp_credentials_dir):
        store = PlaintextStore()
        store.save(SAMPLE_CREDENTIALS)
        assert temp_credentials_dir.exists()

    def test_save_sets_permissions(self, temp_credentials_dir):
        store = PlaintextStore()
        store.save(SAMPLE_CREDENTIALS)
        cred_file = temp_credentials_dir / "credentials"
        mode = oct(cred_file.stat().st_mode & 0o777)
        assert mode == "0o600"

    def test_save_and_load_roundtrip(self, temp_credentials_dir):
        store = PlaintextStore()
        store.save(SAMPLE_CREDENTIALS)
        loaded = store.load()
        assert loaded == SAMPLE_CREDENTIALS

    def test_load_returns_none_when_missing(self, temp_credentials_dir):
        store = PlaintextStore()
        assert store.load() is None

    def test_load_returns_none_for_invalid_json(self, temp_credentials_dir):
        cred_file = temp_credentials_dir / "credentials"
        temp_credentials_dir.mkdir(parents=True, exist_ok=True)
        cred_file.write_text("not-json{{{")
        store = PlaintextStore()
        assert store.load() is None

    def test_clear_removes_file(self, temp_credentials_dir):
        store = PlaintextStore()
        store.save(SAMPLE_CREDENTIALS)
        assert store.clear() is True
        assert store.load() is None

    def test_clear_returns_false_when_missing(self, temp_credentials_dir):
        store = PlaintextStore()
        assert store.clear() is False

    def test_name(self):
        assert PlaintextStore().name == "plaintext"


# ──────────────────────────────────────────────────────────────────
# KeyringStore tests (mocked keyring)
# ──────────────────────────────────────────────────────────────────


class TestKeyringStore:
    """Tests for the KeyringStore backend using mocked keyring."""

    @pytest.fixture
    def mock_keyring(self):
        """Mock the keyring module."""
        storage = {}

        mock = MagicMock()

        def set_password(service, username, password):
            storage[(service, username)] = password

        def get_password(service, username):
            return storage.get((service, username))

        def delete_password(service, username):
            if (service, username) in storage:
                del storage[(service, username)]
            else:
                raise mock.errors.PasswordDeleteError("not found")

        mock.set_password = set_password
        mock.get_password = get_password
        mock.delete_password = delete_password
        mock.errors = MagicMock()
        mock.errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})

        with patch.dict("sys.modules", {"keyring": mock, "keyring.errors": mock.errors}):
            yield mock, storage

    def test_save_and_load_roundtrip(self, mock_keyring):
        store = KeyringStore()
        store.save(SAMPLE_CREDENTIALS)
        loaded = store.load()
        assert loaded == SAMPLE_CREDENTIALS

    def test_load_returns_none_when_empty(self, mock_keyring):
        store = KeyringStore()
        assert store.load() is None

    def test_load_returns_none_for_invalid_data(self, mock_keyring):
        mock_kr, storage = mock_keyring
        storage[(KEYRING_SERVICE, KEYRING_USERNAME)] = "not-json{{{"
        store = KeyringStore()
        assert store.load() is None

    def test_clear_removes_entry(self, mock_keyring):
        store = KeyringStore()
        store.save(SAMPLE_CREDENTIALS)
        assert store.clear() is True
        assert store.load() is None

    def test_clear_returns_false_when_empty(self, mock_keyring):
        store = KeyringStore()
        assert store.clear() is False

    def test_name(self):
        assert KeyringStore().name == "keyring"


# ──────────────────────────────────────────────────────────────────
# Backend detection tests
# ──────────────────────────────────────────────────────────────────


def _make_backend_class(module: str, qualname: str):
    """Create a mock backend class with the given module and qualname."""
    cls = type(qualname, (), {})
    cls.__module__ = module
    cls.__qualname__ = qualname
    return cls


class TestBackendDetection:
    """Tests for _keyring_backend_is_viable."""

    def test_viable_macos_backend(self):
        BackendCls = _make_backend_class("keyring.backends.macOS", "Keyring")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is True

    def test_fail_backend_not_viable(self):
        BackendCls = _make_backend_class("keyring.backends.fail", "Keyring")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_chainer_with_viable_backends(self):
        ChainerCls = _make_backend_class("keyring.backends.chainer", "ChainerBackend")
        ViableCls = _make_backend_class("keyring.backends.macOS", "Keyring")

        chainer = ChainerCls()
        chainer.backends = [ViableCls()]

        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = chainer

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is True

    def test_chainer_with_only_fail_backends(self):
        ChainerCls = _make_backend_class("keyring.backends.chainer", "ChainerBackend")
        FailCls = _make_backend_class("keyring.backends.fail", "Keyring")

        chainer = ChainerCls()
        chainer.backends = [FailCls()]

        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = chainer

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_runtime_keychain_error_not_viable(self):
        """macOS Keychain error -25308 over SSH makes backend not viable."""
        BackendCls = _make_backend_class("keyring.backends.macOS", "Keyring")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()

        # Simulate the macOS Keychain error that occurs over SSH
        KeyringError = type("KeyringError", (Exception,), {})
        mock_keyring.get_password.side_effect = KeyringError(
            "Can't get password from keychain: (-25308, 'Unknown Error')"
        )

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_chainer_with_runtime_keychain_error(self):
        """Chainer backend with viable type but runtime failure is not viable."""
        ChainerCls = _make_backend_class("keyring.backends.chainer", "ChainerBackend")
        ViableCls = _make_backend_class("keyring.backends.macOS", "Keyring")

        chainer = ChainerCls()
        chainer.backends = [ViableCls()]

        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = chainer
        mock_keyring.get_password.side_effect = OSError("Keychain access denied")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_secretservice_runtime_dbus_error(self):
        """Linux SecretService backend fails when DBus is unavailable."""
        BackendCls = _make_backend_class(
            "keyring.backends.SecretService", "Keyring"
        )
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()
        mock_keyring.get_password.side_effect = Exception(
            "org.freedesktop.DBus.Error.ServiceUnknown"
        )

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_runtime_permission_error(self):
        """PermissionError from keychain probe makes backend not viable."""
        BackendCls = _make_backend_class("keyring.backends.macOS", "Keyring")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()
        mock_keyring.get_password.side_effect = PermissionError(
            "Keychain access not permitted"
        )

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_runtime_error_generic(self):
        """Generic RuntimeError from keychain probe makes backend not viable."""
        BackendCls = _make_backend_class(
            "keyring.backends.kwallet", "DBusKeyring"
        )
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()
        mock_keyring.get_password.side_effect = RuntimeError(
            "KWallet service not available"
        )

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is False

    def test_probe_succeeds_backend_viable(self):
        """Backend is viable when type check and probe both pass."""
        BackendCls = _make_backend_class("keyring.backends.macOS", "Keyring")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()
        mock_keyring.get_password.return_value = None  # probe returns None (no stored value)

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            assert _keyring_backend_is_viable() is True

    def test_import_error_not_viable(self):
        with patch.dict("sys.modules", {"keyring": None}):
            assert _keyring_backend_is_viable() is False


# ──────────────────────────────────────────────────────────────────
# Migration tests
# ──────────────────────────────────────────────────────────────────


class TestMigration:
    """Tests for plaintext-to-keyring migration."""

    @pytest.fixture(autouse=True)
    def temp_credentials_dir(self, tmp_path, monkeypatch):
        cred_dir = tmp_path / ".voicemode"
        cred_dir.mkdir(parents=True)
        cred_file = cred_dir / "credentials"
        migrated_file = cred_dir / "credentials.migrated"
        monkeypatch.setattr("voice_mode.credential_store.CREDENTIALS_DIR", cred_dir)
        monkeypatch.setattr("voice_mode.credential_store.CREDENTIALS_FILE", cred_file)
        monkeypatch.setattr("voice_mode.credential_store.CREDENTIALS_MIGRATED_FILE", migrated_file)
        return cred_dir

    def test_migrates_plaintext_to_keyring(self, temp_credentials_dir):
        """Plaintext credentials are moved to keyring and file renamed."""
        cred_file = temp_credentials_dir / "credentials"
        cred_file.write_text(json.dumps(SAMPLE_CREDENTIALS))

        keyring_storage = {}

        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None
        mock_kr.set_password.side_effect = lambda s, u, p: keyring_storage.update({(s, u): p})

        with patch.dict("sys.modules", {"keyring": mock_kr}):
            store = KeyringStore()
            _migrate_plaintext_to_keyring(store)

        # Plaintext file should be renamed
        assert not cred_file.exists()
        assert (temp_credentials_dir / "credentials.migrated").exists()

        # Keyring should have the data
        assert (KEYRING_SERVICE, KEYRING_USERNAME) in keyring_storage

    def test_no_migration_when_keyring_has_data(self, temp_credentials_dir):
        """Skip migration if keyring already has credentials."""
        cred_file = temp_credentials_dir / "credentials"
        cred_file.write_text(json.dumps(SAMPLE_CREDENTIALS))

        mock_kr = MagicMock()
        mock_kr.get_password.return_value = json.dumps(SAMPLE_CREDENTIALS)

        with patch.dict("sys.modules", {"keyring": mock_kr}):
            store = KeyringStore()
            _migrate_plaintext_to_keyring(store)

        # Plaintext file should still exist (not migrated)
        assert cred_file.exists()

    def test_no_migration_when_no_plaintext(self, temp_credentials_dir):
        """No crash when there's nothing to migrate."""
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None

        with patch.dict("sys.modules", {"keyring": mock_kr}):
            store = KeyringStore()
            _migrate_plaintext_to_keyring(store)  # should not raise


# ──────────────────────────────────────────────────────────────────
# get_credential_store tests
# ──────────────────────────────────────────────────────────────────


class TestGetCredentialStore:
    """Tests for the store selection logic."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset the singleton cache between tests."""
        cred_mod._cached_store = None
        yield
        cred_mod._cached_store = None

    def test_plaintext_when_configured(self, monkeypatch):
        monkeypatch.setenv("VOICEMODE_CREDENTIAL_STORE", "plaintext")
        store = get_credential_store()
        assert isinstance(store, PlaintextStore)

    def test_keyring_when_configured_and_viable(self, monkeypatch):
        monkeypatch.setenv("VOICEMODE_CREDENTIAL_STORE", "keyring")
        with patch("voice_mode.credential_store._keyring_backend_is_viable", return_value=True), \
             patch("voice_mode.credential_store._migrate_plaintext_to_keyring"):
            store = get_credential_store()
            assert isinstance(store, KeyringStore)

    def test_fallback_to_plaintext_when_keyring_unavailable(self, monkeypatch):
        monkeypatch.setenv("VOICEMODE_CREDENTIAL_STORE", "keyring")
        with patch("voice_mode.credential_store._keyring_backend_is_viable", return_value=False):
            store = get_credential_store()
            assert isinstance(store, PlaintextStore)

    def test_default_is_plaintext(self, monkeypatch):
        """When VOICEMODE_CREDENTIAL_STORE is unset, default to plaintext."""
        monkeypatch.delenv("VOICEMODE_CREDENTIAL_STORE", raising=False)
        store = get_credential_store()
        assert isinstance(store, PlaintextStore)

    def test_singleton_cache_returns_same_instance(self, monkeypatch):
        """Repeated calls return the cached instance."""
        monkeypatch.delenv("VOICEMODE_CREDENTIAL_STORE", raising=False)
        store1 = get_credential_store()
        store2 = get_credential_store()
        assert store1 is store2

    def test_fallback_on_keychain_runtime_error(self, monkeypatch):
        """Keychain runtime errors (e.g. SSH -25308) trigger plaintext fallback."""
        monkeypatch.setenv("VOICEMODE_CREDENTIAL_STORE", "keyring")

        BackendCls = _make_backend_class("keyring.backends.macOS", "Keyring")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = BackendCls()
        mock_keyring.get_password.side_effect = Exception(
            "Can't get password from keychain: (-25308, 'Unknown Error')"
        )

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            store = get_credential_store()
            assert isinstance(store, PlaintextStore)
