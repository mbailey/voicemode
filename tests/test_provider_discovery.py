"""Unit tests for provider_discovery.detect_provider_type and is_local_provider."""

import pytest

from voice_mode.provider_discovery import detect_provider_type, is_local_provider


class TestDetectProviderType:
    """Cover the provider-type ladder including the mlx-audio branch (VM-1106)."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://api.openai.com/v1", "openai"),
            ("http://127.0.0.1:8880/v1", "kokoro"),
            ("http://127.0.0.1:2022/v1", "whisper"),
            ("http://127.0.0.1:8890/v1", "mlx-audio"),
            ("http://localhost:8890", "mlx-audio"),
        ],
    )
    def test_known_provider_types(self, url, expected):
        assert detect_provider_type(url) == expected

    def test_mlx_audio_substring_fallback(self):
        # Reverse-proxied / non-default-port deployments still match via
        # host/path substring per VM-1106 design.
        assert detect_provider_type("http://example.com/mlx_audio/v1") == "mlx-audio"
        assert detect_provider_type("http://example.com/mlx-audio/v1") == "mlx-audio"

    def test_unknown_url_falls_through(self):
        # Non-localhost, non-OpenAI URLs without mlx-audio markers should
        # remain "unknown" -- this is the existing default behaviour.
        assert detect_provider_type("https://api.example.com/v1") == "unknown"

    def test_empty_base_url(self):
        assert detect_provider_type("") == "unknown"

    def test_generic_local_unchanged(self):
        # A localhost endpoint on an unrecognised port still falls back to
        # the generic "local" provider type (regression check).
        assert detect_provider_type("http://127.0.0.1:9999/v1") == "local"


class TestIsLocalProvider:
    """is_local_provider must treat mlx-audio as local (VM-1106 AC item 6)."""

    def test_mlx_audio_localhost_is_local(self):
        assert is_local_provider("http://127.0.0.1:8890/v1") is True

    def test_mlx_audio_reverse_proxy_is_local(self):
        # Even off-localhost mlx-audio endpoints should be classified local
        # via the provider_type allowlist.
        assert is_local_provider("http://example.com/mlx_audio/v1") is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:8880/v1",
            "http://localhost:2022/v1",
            "http://127.0.0.1:9999/v1",
        ],
    )
    def test_existing_local_providers_unchanged(self, url):
        assert is_local_provider(url) is True

    def test_openai_is_not_local(self):
        assert is_local_provider("https://api.openai.com/v1") is False

    def test_empty_base_url_is_not_local(self):
        assert is_local_provider("") is False
