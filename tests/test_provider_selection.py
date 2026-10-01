"""Tests for voice-first provider selection logic."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from voice_mode.provider_discovery import (
    ProviderRegistry,
    EndpointInfo,
    detect_provider_type,
    _default_tts_models,
)
from voice_mode.providers import (
    get_tts_client_and_voice,
    _select_model_for_endpoint,
    _select_stt_model_for_endpoint,
    _select_tts_model_for_endpoint,
    _model_compatible,
)


class TestProviderTypeDetection:
    """Test provider type detection from URLs."""
    
    def test_detect_openai(self):
        assert detect_provider_type("https://api.openai.com/v1") == "openai"
        assert detect_provider_type("https://api.openai.com/v1/") == "openai"
    
    def test_detect_kokoro(self):
        assert detect_provider_type("http://127.0.0.1:8880/v1") == "kokoro"
        assert detect_provider_type("http://127.0.0.1:8880/v1") == "kokoro"
        assert detect_provider_type("http://192.168.1.100:8880/v1") == "kokoro"
    
    def test_detect_whisper(self):
        assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
        assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
    
    def test_detect_generic_local(self):
        assert detect_provider_type("http://127.0.0.1:9999/v1") == "local"
        assert detect_provider_type("http://127.0.0.1/api") == "local"
    
    def test_detect_unknown(self):
        assert detect_provider_type("https://example.com/api") == "unknown"
        assert detect_provider_type("http://external-server.com:8080/v1") == "unknown"


class TestVoiceFirstSelection:
    """Test the voice-first provider selection algorithm."""
    
    @pytest.fixture(autouse=True)
    def mock_voice_preferences(self):
        """Mock voice preferences to avoid test pollution."""
        with patch('voice_mode.providers.get_voice_preferences', return_value=[]):
            yield
    
    @pytest.fixture
    def mock_registry(self):
        """Create a mock provider registry with test data."""
        registry = ProviderRegistry()
        registry._initialized = True
        
        # Mock Kokoro endpoint with af_sky voice
        registry.registry["tts"]["http://127.0.0.1:8880/v1"] = EndpointInfo(
            base_url="http://127.0.0.1:8880/v1",
            models=["tts-1"],
            voices=["af_sky", "af_sarah", "am_adam"],
            provider_type="kokoro"
        )

        # Mock OpenAI endpoint with standard voices
        registry.registry["tts"]["https://api.openai.com/v1"] = EndpointInfo(
            base_url="https://api.openai.com/v1",
            models=["tts-1", "tts-1-hd", "gpt-4o-mini-tts"],
            voices=["alloy", "echo", "fable", "nova", "onyx", "shimmer"],
            provider_type="openai"
        )
        
        return registry
    
    @pytest.mark.asyncio
    async def test_voice_first_selects_kokoro_for_af_sky(self, mock_registry):
        """Test that af_sky voice preference selects Kokoro."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.get_voice_preferences', return_value=['af_sky', 'alloy']):
                with patch('voice_mode.providers.TTS_MODELS', ['tts-1', 'tts-1-hd']):
                    with patch('voice_mode.providers.TTS_BASE_URLS', [
                        'http://127.0.0.1:8880/v1',
                        'https://api.openai.com/v1'
                    ]):
                        client, voice, model, endpoint = await get_tts_client_and_voice()
                        
                        assert voice == "af_sky"
                        assert endpoint.provider_type == "kokoro"
                        assert endpoint.base_url == "http://127.0.0.1:8880/v1"
    
    @pytest.mark.asyncio
    async def test_voice_first_selects_openai_for_nova(self, mock_registry):
        """Test that nova voice preference selects OpenAI."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.get_voice_preferences', return_value=['nova', 'af_sky']):
                with patch('voice_mode.providers.TTS_MODELS', ['tts-1-hd', 'tts-1']):
                    with patch('voice_mode.providers.TTS_BASE_URLS', [
                        'http://127.0.0.1:8880/v1',
                        'https://api.openai.com/v1'
                    ]):
                        client, voice, model, endpoint = await get_tts_client_and_voice()
                        
                        assert voice == "nova"
                        assert endpoint.provider_type == "openai"
                        assert endpoint.base_url == "https://api.openai.com/v1"
                        assert model == "tts-1-hd"  # First available from preference
    
    @pytest.mark.asyncio
    async def test_specific_voice_overrides_preferences(self, mock_registry):
        """Test that specific voice request overrides preferences."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.get_voice_preferences', return_value=['nova', 'alloy']):
                with patch('voice_mode.providers.TTS_BASE_URLS', [
                    'http://127.0.0.1:8880/v1',
                    'https://api.openai.com/v1'
                ]):
                    client, voice, model, endpoint = await get_tts_client_and_voice(voice="af_sarah")
                    
                    assert voice == "af_sarah"
                    assert endpoint.provider_type == "kokoro"
    
    @pytest.mark.asyncio
    async def test_endpoint_with_error_still_tried(self, mock_registry):
        """Test that endpoints with errors are still tried (no health concept)."""
        # Mark Kokoro as having an error (but it's still tried)
        mock_registry.registry["tts"]["http://127.0.0.1:8880/v1"].last_error = "Previous connection failed"

        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.get_voice_preferences', return_value=['af_sky', 'nova']):
                with patch('voice_mode.providers.TTS_BASE_URLS', [
                    'http://127.0.0.1:8880/v1',
                    'https://api.openai.com/v1'
                ]):
                    client, voice, model, endpoint = await get_tts_client_and_voice()

                    # Should still try Kokoro first since af_sky is preferred and available
                    assert voice == "af_sky"
                    assert endpoint.provider_type == "kokoro"
    
    @pytest.mark.asyncio
    async def test_model_selection_respects_provider_models(self, mock_registry):
        """Test that model selection respects what the provider supports."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.get_voice_preferences', return_value=['af_sky']):
                with patch('voice_mode.providers.TTS_MODELS', ['gpt-4o-mini-tts', 'tts-1-hd', 'tts-1']):
                    with patch('voice_mode.providers.TTS_BASE_URLS', [
                        'http://127.0.0.1:8880/v1',
                        'https://api.openai.com/v1'
                    ]):
                        client, voice, model, endpoint = await get_tts_client_and_voice()
                        
                        # Kokoro only supports tts-1, so it should select that
                        assert voice == "af_sky"
                        assert model == "tts-1"
                        assert endpoint.provider_type == "kokoro"


class TestModelSelection:
    """Test model selection for endpoints."""
    
    def test_select_requested_model_if_available(self):
        endpoint = EndpointInfo(
            base_url="test",
            models=["tts-1", "tts-1-hd"],
            voices=[],
            provider_type="test",
            last_check="",
            last_error=None
        )
        
        assert _select_model_for_endpoint(endpoint, "tts-1-hd") == "tts-1-hd"
    
    def test_select_preferred_model(self):
        endpoint = EndpointInfo(
            base_url="test",
            models=["tts-1", "tts-1-hd"],
            voices=[],
            provider_type="test",
            last_check="",
            last_error=None
        )
        
        with patch('voice_mode.providers.TTS_MODELS', ['gpt-4o-mini-tts', 'tts-1-hd', 'tts-1']):
            # Should pick tts-1-hd as it's the first available from preferences
            assert _select_model_for_endpoint(endpoint) == "tts-1-hd"
    
    def test_fallback_to_first_available(self):
        endpoint = EndpointInfo(
            base_url="test",
            models=["custom-model"],
            voices=[],
            provider_type="test",
            last_check="",
            last_error=None
        )
        
        with patch('voice_mode.providers.TTS_MODELS', ['tts-1', 'tts-1-hd']):
            # No preferred models available, use first
            assert _select_model_for_endpoint(endpoint) == "custom-model"
    
    def test_default_fallback(self):
        endpoint = EndpointInfo(
            base_url="test",
            models=[],
            voices=[],
            provider_type="test",
            last_check="",
            last_error=None
        )

        # No advertised models: fall back via the provider-aware resolver
        # (VM-1390). A generic provider accepts any model, so it lands on the
        # first global TTS_MODELS entry. Pin the config so this is deterministic
        # regardless of the ambient VOICEMODE_TTS_MODELS.
        with patch('voice_mode.providers.TTS_MODELS', ['tts-1', 'tts-1-hd', 'gpt-4o-mini-tts']), \
             patch('voice_mode.providers.TTS_MODELS_BY_PROVIDER', {}):
            assert _select_model_for_endpoint(endpoint) == "tts-1"


class TestSttModelSelection:
    """Tests for _select_stt_model_for_endpoint resolver branches."""

    def _make_endpoint(self, base_url: str, provider_type: str) -> EndpointInfo:
        return EndpointInfo(
            base_url=base_url,
            models=[],
            voices=[],
            provider_type=provider_type,
            last_check="",
            last_error=None,
        )

    def test_openai_override_returns_whisper_1_regardless_of_requested(self):
        """Branch 1: provider_type == 'openai' always returns 'whisper-1',
        even when caller passes a different model and STT_MODELS configures
        a positional override."""
        endpoint = self._make_endpoint("https://api.openai.com/v1", "openai")
        with patch(
            "voice_mode.providers.STT_BASE_URLS",
            ["https://api.openai.com/v1"],
        ), patch(
            "voice_mode.providers.STT_MODELS",
            ["mlx-community/whisper-large-v3-turbo"],
        ), patch("voice_mode.providers.STT_MODEL", "global-default"):
            assert _select_stt_model_for_endpoint(endpoint) == "whisper-1"
            assert (
                _select_stt_model_for_endpoint(endpoint, "caller-passed")
                == "whisper-1"
            )

    def test_caller_passed_wins_for_non_openai(self):
        """Branch 2: caller-passed requested_model is honored for non-OpenAI
        providers (whisper.cpp, mlx-audio, openai-compatible, unknown)."""
        for provider_type in (
            "whisper",
            "mlx-audio",
            "openai-compatible",
            "unknown-provider",
        ):
            endpoint = self._make_endpoint(
                "http://127.0.0.1:2022/v1", provider_type
            )
            with patch(
                "voice_mode.providers.STT_BASE_URLS",
                ["http://127.0.0.1:2022/v1"],
            ), patch(
                "voice_mode.providers.STT_MODELS", ["positional-model"]
            ), patch("voice_mode.providers.STT_MODEL", "global-default"):
                assert (
                    _select_stt_model_for_endpoint(endpoint, "caller-model")
                    == "caller-model"
                ), f"caller-passed should win for provider_type={provider_type}"

    def test_positional_stt_models_used_when_caller_passed_is_none(self):
        """Branch 3: when caller-passed is None and the endpoint URL is in
        STT_BASE_URLS at index N, return STT_MODELS[N] if non-empty."""
        urls = [
            "http://127.0.0.1:8890/v1",
            "http://127.0.0.1:2022/v1",
            "https://api.openai.com/v1",
        ]
        models = [
            "mlx-community/whisper-large-v3-turbo",
            "custom-cpp-model",
            "whisper-1",
        ]
        with patch("voice_mode.providers.STT_BASE_URLS", urls), patch(
            "voice_mode.providers.STT_MODELS", models
        ), patch("voice_mode.providers.STT_MODEL", "global-default"):
            mlx = self._make_endpoint(urls[0], "mlx-audio")
            cpp = self._make_endpoint(urls[1], "whisper")
            assert (
                _select_stt_model_for_endpoint(mlx)
                == "mlx-community/whisper-large-v3-turbo"
            )
            assert _select_stt_model_for_endpoint(cpp) == "custom-cpp-model"

    def test_global_stt_model_fallback_when_no_positional(self):
        """Branch 4: fallback to global STT_MODEL when caller-passed is None
        and no positional STT_MODELS entry applies (URL not in STT_BASE_URLS,
        index out of range, or positional entry empty)."""
        with patch(
            "voice_mode.providers.STT_BASE_URLS",
            ["http://127.0.0.1:2022/v1"],
        ), patch("voice_mode.providers.STT_MODELS", []), patch(
            "voice_mode.providers.STT_MODEL", "global-default"
        ):
            # URL not in STT_BASE_URLS
            unknown = self._make_endpoint(
                "http://10.0.0.5:9999/v1", "unknown-provider"
            )
            assert _select_stt_model_for_endpoint(unknown) == "global-default"
            # URL in STT_BASE_URLS but STT_MODELS empty (idx out of range)
            cpp = self._make_endpoint("http://127.0.0.1:2022/v1", "whisper")
            assert _select_stt_model_for_endpoint(cpp) == "global-default"

        # Positional entry exists but is empty -> falls back to global
        with patch(
            "voice_mode.providers.STT_BASE_URLS",
            ["http://127.0.0.1:2022/v1"],
        ), patch("voice_mode.providers.STT_MODELS", [""]), patch(
            "voice_mode.providers.STT_MODEL", "global-default"
        ):
            cpp = self._make_endpoint("http://127.0.0.1:2022/v1", "whisper")
            assert _select_stt_model_for_endpoint(cpp) == "global-default"

    # VM-2342: steps 4-5, the per-provider STT default for mlx-audio.

    def test_mlx_audio_stock_default_replaces_whisper_1(self):
        """VOICEMODE_STT_MODEL unset: the "whisper-1" fallback is an OpenAI id
        mlx-audio 404s on, so the built-in mlx-audio default is sent."""
        with patch("voice_mode.providers.STT_BASE_URLS", []), patch(
            "voice_mode.providers.STT_MODELS", []
        ), patch("voice_mode.providers.STT_MODEL", "whisper-1"), patch(
            "voice_mode.providers.STT_MODEL_EXPLICIT", False
        ):
            mlx = self._make_endpoint("http://127.0.0.1:8890/v1", "mlx-audio")
            assert (
                _select_stt_model_for_endpoint(mlx)
                == "mlx-community/whisper-large-v3-turbo-asr-4bit"
            )
            # Non-mlx providers keep the global fallback.
            cpp = self._make_endpoint("http://127.0.0.1:2022/v1", "whisper")
            assert _select_stt_model_for_endpoint(cpp) == "whisper-1"

    def test_explicit_stt_model_beats_mlx_audio_default(self):
        with patch("voice_mode.providers.STT_BASE_URLS", []), patch(
            "voice_mode.providers.STT_MODELS", []
        ), patch("voice_mode.providers.STT_MODEL", "whisper-1"), patch(
            "voice_mode.providers.STT_MODEL_EXPLICIT", True
        ):
            mlx = self._make_endpoint("http://127.0.0.1:8890/v1", "mlx-audio")
            assert _select_stt_model_for_endpoint(mlx) == "whisper-1"

    def test_repo_id_stt_model_beats_mlx_audio_default(self):
        """A global STT_MODEL mlx-audio can load (repo id) is used as-is."""
        with patch("voice_mode.providers.STT_BASE_URLS", []), patch(
            "voice_mode.providers.STT_MODELS", []
        ), patch("voice_mode.providers.STT_MODEL", "org/some-asr"), patch(
            "voice_mode.providers.STT_MODEL_EXPLICIT", False
        ):
            mlx = self._make_endpoint("http://127.0.0.1:8890/v1", "mlx-audio")
            assert _select_stt_model_for_endpoint(mlx) == "org/some-asr"


DEFAULT_TTS_MODELS = ["tts-1", "tts-1-hd", "gpt-4o-mini-tts"]


class TestModelCompatible:
    """Tests for the _model_compatible provider/model heuristic (VM-1390)."""

    def test_mlx_audio_requires_repo_id(self):
        assert _model_compatible("mlx-audio", "mlx-community/Kokoro-82M-bf16")
        assert not _model_compatible("mlx-audio", "tts-1")

    def test_kokoro_and_openai_require_plain_id(self):
        for pt in ("kokoro", "openai"):
            assert _model_compatible(pt, "tts-1")
            assert not _model_compatible(pt, "some/repo-id")

    def test_local_unknown_cartesia_accept_anything(self):
        for pt in ("local", "unknown", "cartesia"):
            assert _model_compatible(pt, "tts-1")
            assert _model_compatible(pt, "some/repo-id")


class TestTtsModelSelection:
    """Tests for _select_tts_model_for_endpoint resolution order (VM-1390)."""

    def test_defaults_per_provider(self):
        """With the default global TTS_MODELS and no per-provider env,
        each provider type resolves to the right model."""
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            assert _select_tts_model_for_endpoint("kokoro") == "tts-1"
            assert _select_tts_model_for_endpoint("openai") == "tts-1"
            assert (
                _select_tts_model_for_endpoint("mlx-audio")
                == "mlx-community/Kokoro-82M-bf16"
            )
            assert _select_tts_model_for_endpoint("local") == "tts-1"
            assert _select_tts_model_for_endpoint("unknown") == "tts-1"

    def test_global_set_to_mlx_repo_id_mikes_env(self):
        """Global TTS_MODELS set to an mlx repo id (Mike's env workaround):
        mlx-audio gets that repo via step 3; kokoro skips the incompatible
        repo id and falls to its built-in default 'tts-1'."""
        with patch(
            "voice_mode.providers.TTS_MODELS",
            ["mlx-community/Kokoro-82M-bf16"],
        ), patch("voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}):
            assert (
                _select_tts_model_for_endpoint("mlx-audio")
                == "mlx-community/Kokoro-82M-bf16"
            )
            assert _select_tts_model_for_endpoint("kokoro") == "tts-1"
            assert _select_tts_model_for_endpoint("openai") == "tts-1"

    def test_per_provider_env_beats_global_and_default(self):
        """VOICEMODE_TTS_MODELS_<PROVIDER> (parsed into TTS_MODELS_BY_PROVIDER)
        wins over the compatible-global-entry and built-in-default steps."""
        by_provider = {
            "mlx-audio": ["mlx-community/Other-Repo"],
            "kokoro": ["tts-1-hd"],
            "openai": ["gpt-4o-mini-tts"],
        }
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", by_provider
        ):
            assert (
                _select_tts_model_for_endpoint("mlx-audio")
                == "mlx-community/Other-Repo"
            )
            assert _select_tts_model_for_endpoint("kokoro") == "tts-1-hd"
            assert _select_tts_model_for_endpoint("openai") == "gpt-4o-mini-tts"

    def test_explicit_requested_model_wins_for_every_provider(self):
        """Step 1: an explicit caller model is sent as-is, over per-provider
        env, compatible-global, and built-in default -- for every provider."""
        by_provider = {"mlx-audio": ["mlx-community/Other-Repo"]}
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", by_provider
        ):
            for pt in ("kokoro", "openai", "mlx-audio", "local", "unknown"):
                assert (
                    _select_tts_model_for_endpoint(pt, "caller-choice")
                    == "caller-choice"
                )

    def test_select_model_for_endpoint_fallback_is_provider_aware(self):
        """The registry path's _select_model_for_endpoint fallback (no advertised
        models) now yields the provider-aware default, not a hardcoded 'tts-1'."""
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            mlx = EndpointInfo(
                base_url="http://127.0.0.1:8890/v1",
                models=[],
                voices=[],
                provider_type="mlx-audio",
            )
            assert (
                _select_model_for_endpoint(mlx)
                == "mlx-community/Kokoro-82M-bf16"
            )
            kokoro = EndpointInfo(
                base_url="http://127.0.0.1:8880/v1",
                models=[],
                voices=[],
                provider_type="kokoro",
            )
            assert _select_model_for_endpoint(kokoro) == "tts-1"


class TestRegistrySeedHardening:
    """VM-2156: the registry seed must never advertise an id mlx-audio cannot
    load, and selection must not hand one on even if a stale seed exists.

    Hardening of the seeded/diagnostics path -- the live speech path already
    resolves through _select_tts_model_for_endpoint (VM-1390).
    """

    def test_mlx_audio_seed_is_a_repo_id_not_tts_1(self):
        """The seed for a :8890 endpoint is an HF repo id, matching the
        provider-aware default (single source: TTS_MODEL_PROVIDER_DEFAULTS)."""
        seeded = _default_tts_models("http://127.0.0.1:8890/v1")
        assert seeded == ["mlx-community/Kokoro-82M-bf16"]
        assert "tts-1" not in seeded
        assert _model_compatible("mlx-audio", seeded[0])

    def test_non_mlx_seeds_are_unchanged(self):
        """kokoro / generic-local / unknown keep the historical 'tts-1' seed."""
        for url in (
            "http://127.0.0.1:8880/v1",
            "http://127.0.0.1:9999/v1",
            "https://example.com/v1",
        ):
            assert _default_tts_models(url) == ["tts-1"]

    @pytest.mark.asyncio
    async def test_registry_initialize_seeds_and_selects_a_repo_id_for_8890(self):
        """End to end over the seeded path: initialize() then
        _select_model_for_endpoint() yields a model containing '/' for the
        mlx-audio endpoint, and a plain id for kokoro."""
        urls = ["http://127.0.0.1:8890/v1", "http://127.0.0.1:8880/v1"]
        with patch("voice_mode.provider_discovery.TTS_BASE_URLS", urls), patch(
            "voice_mode.provider_discovery.STT_BASE_URLS", []
        ), patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            registry = ProviderRegistry()
            await registry.initialize()

            mlx = registry.registry["tts"]["http://127.0.0.1:8890/v1"]
            assert mlx.provider_type == "mlx-audio"
            assert "tts-1" not in mlx.models
            chosen = _select_model_for_endpoint(mlx)
            assert "/" in chosen
            assert _model_compatible("mlx-audio", chosen)

            kokoro = registry.registry["tts"]["http://127.0.0.1:8880/v1"]
            assert _select_model_for_endpoint(kokoro) == "tts-1"

    def test_stale_incompatible_seed_is_filtered_out(self):
        """Even with a stale ['tts-1'] seed (old install, or an endpoint that
        advertises ids it cannot load), mlx-audio is never sent 'tts-1'."""
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            stale = EndpointInfo(
                base_url="http://127.0.0.1:8890/v1",
                models=["tts-1", "tts-1-hd"],
                voices=[],
                provider_type="mlx-audio",
            )
            assert (
                _select_model_for_endpoint(stale)
                == "mlx-community/Kokoro-82M-bf16"
            )

    def test_compatible_advertised_models_still_win(self):
        """The filter narrows, it does not override: a compatible advertised
        model is still preferred over the built-in default."""
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            endpoint = EndpointInfo(
                base_url="http://127.0.0.1:8890/v1",
                models=["tts-1", "mlx-community/Other-Repo"],
                voices=[],
                provider_type="mlx-audio",
            )
            assert (
                _select_model_for_endpoint(endpoint)
                == "mlx-community/Other-Repo"
            )

    def test_explicit_requested_model_is_still_honoured(self):
        """Caller trust (step 1) is unchanged by the filter."""
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            endpoint = EndpointInfo(
                base_url="http://127.0.0.1:8890/v1",
                models=["mlx-community/Kokoro-82M-bf16"],
                voices=[],
                provider_type="mlx-audio",
            )
            assert (
                _select_model_for_endpoint(
                    endpoint, "mlx-community/Kokoro-82M-bf16"
                )
                == "mlx-community/Kokoro-82M-bf16"
            )

    def test_kokoro_seed_selection_is_unaffected(self):
        """Regression guard: the 8880 (kokoro) path keeps its plain id."""
        with patch("voice_mode.providers.TTS_MODELS", DEFAULT_TTS_MODELS), patch(
            "voice_mode.providers.TTS_MODELS_BY_PROVIDER", {}
        ):
            kokoro = EndpointInfo(
                base_url="http://127.0.0.1:8880/v1",
                models=_default_tts_models("http://127.0.0.1:8880/v1"),
                voices=[],
                provider_type="kokoro",
            )
            assert _select_model_for_endpoint(kokoro) == "tts-1"
