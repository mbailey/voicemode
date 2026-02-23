"""Tests for voice_mode.connect.config."""

import importlib
import pytest

import voice_mode.config as cfg
from voice_mode.connect.config import (
    ConnectDisabledError,
    get_agent_name,
    get_host,
    get_preconfigured_users,
    get_ws_url,
    is_enabled,
    require_enabled,
)


class TestIsEnabled:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_ENABLED", False)
        assert is_enabled() is False

    def test_enabled_when_set(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_ENABLED", True)
        assert is_enabled() is True


class TestBackwardCompat:
    def test_old_env_var_enables_connect(self, monkeypatch):
        """VOICEMODE_CONNECT_AUTO=true should set CONNECT_ENABLED=True."""
        monkeypatch.delenv("VOICEMODE_CONNECT_ENABLED", raising=False)
        monkeypatch.setenv("VOICEMODE_CONNECT_AUTO", "true")
        importlib.reload(cfg)
        assert cfg.CONNECT_ENABLED is True


class TestGetPreconfiguredUsers:
    def test_parses_comma_separated(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_USERS", ["alice", "bob", "charlie"])
        assert get_preconfigured_users() == ["alice", "bob", "charlie"]

    def test_handles_empty_string(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_USERS", [])
        assert get_preconfigured_users() == []

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("VOICEMODE_CONNECT_USERS", " alice , bob ")
        importlib.reload(cfg)
        assert get_preconfigured_users() == ["alice", "bob"]


class TestGetHost:
    def test_returns_configured_host(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_HOST", "myhost")
        assert get_host() == "myhost"

    def test_returns_alias_when_set(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_HOST", "custom-alias")
        assert get_host() == "custom-alias"


class TestGetAgentName:
    def test_returns_configured_name(self, monkeypatch):
        monkeypatch.setattr(cfg, "AGENT_NAME", "cora")
        assert get_agent_name() == "cora"

    def test_returns_empty_when_unset(self, monkeypatch):
        monkeypatch.setattr(cfg, "AGENT_NAME", "")
        assert get_agent_name() == ""


class TestGetWsUrl:
    def test_returns_default_ws_url(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_WS_URL", "wss://voicemode.dev/ws")
        assert get_ws_url() == "wss://voicemode.dev/ws"

    def test_returns_custom_ws_url(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_WS_URL", "wss://custom.example.com/ws")
        assert get_ws_url() == "wss://custom.example.com/ws"


class TestGetPreconfiguredUsersFiltersEmpty:
    def test_filters_empty_strings(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_USERS", ["alice", "", "bob", ""])
        assert get_preconfigured_users() == ["alice", "bob"]


class TestRequireEnabled:
    def test_raises_when_disabled(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_ENABLED", False)
        with pytest.raises(ConnectDisabledError):
            require_enabled()

    def test_passes_when_enabled(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_ENABLED", True)
        require_enabled()  # Should not raise

    def test_error_message_includes_instructions(self, monkeypatch):
        monkeypatch.setattr(cfg, "CONNECT_ENABLED", False)
        with pytest.raises(ConnectDisabledError, match="VOICEMODE_CONNECT_ENABLED=true"):
            require_enabled()


class TestConnectDisabledError:
    def test_is_exception_subclass(self):
        assert issubclass(ConnectDisabledError, Exception)
