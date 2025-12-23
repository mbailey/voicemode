"""Tests for custom HTTP header support."""

import os
import pytest
from unittest.mock import patch, MagicMock
from voice_mode.config import parse_extra_headers


class TestHeaderParsing:
    """Test comma-separated header parsing functionality."""

    def test_parse_valid_headers(self):
        """Test parsing valid comma-separated headers."""
        with patch.dict(os.environ, {"TEST_VAR": "X-Custom=value"}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-Custom": "value"}

    def test_parse_multiple_headers(self):
        """Test parsing multiple headers."""
        with patch.dict(os.environ, {
            "TEST_VAR": "X-API-Key=key123,X-Provider=test"
        }):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-API-Key": "key123", "X-Provider": "test"}

    def test_parse_empty_headers(self):
        """Test parsing empty header string."""
        headers = parse_extra_headers("NONEXISTENT_VAR", "")
        assert headers == {}

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty dict."""
        with patch.dict(os.environ, {"TEST_VAR": ""}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {}

    def test_parse_missing_equals(self):
        """Test handling of pairs without equals sign."""
        with patch.dict(os.environ, {"TEST_VAR": "InvalidHeader"}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {}

    def test_parse_empty_key(self):
        """Test handling of empty key."""
        with patch.dict(os.environ, {"TEST_VAR": "=value"}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {}

    def test_parse_value_with_equals(self):
        """Test parsing value that contains equals sign."""
        with patch.dict(os.environ, {"TEST_VAR": "X-Header=value=with=equals"}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-Header": "value=with=equals"}

    def test_parse_with_whitespace(self):
        """Test parsing with extra whitespace."""
        with patch.dict(os.environ, {
            "TEST_VAR": "  X-Custom = value  ,  X-Other = test  "
        }):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-Custom": "value", "X-Other": "test"}

    def test_parse_empty_pairs(self):
        """Test handling of empty pairs (consecutive commas)."""
        with patch.dict(os.environ, {"TEST_VAR": "X-Key=val1,,X-Key2=val2"}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-Key": "val1", "X-Key2": "val2"}

    def test_parse_portkey_example(self):
        """Test parsing real-world Portkey header example."""
        with patch.dict(os.environ, {
            "TEST_VAR": "X-Portkey-API-Key=pk_xxx,X-Portkey-Provider=@openai"
        }):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {
                "X-Portkey-API-Key": "pk_xxx",
                "X-Portkey-Provider": "@openai"
            }

    def test_parse_from_env_var(self):
        """Test reading from actual environment variable."""
        with patch.dict(os.environ, {"VOICEMODE_TEST_HEADERS": "X-Test=value"}):
            headers = parse_extra_headers("VOICEMODE_TEST_HEADERS")
            assert headers == {"X-Test": "value"}

    def test_fallback_value(self):
        """Test fallback parameter when env var not set."""
        headers = parse_extra_headers("NONEXISTENT", "X-Default=value")
        assert headers == {"X-Default": "value"}

    def test_empty_value(self):
        """Test parsing header with empty value."""
        with patch.dict(os.environ, {"TEST_VAR": "X-Header="}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-Header": ""}

    def test_special_characters_in_value(self):
        """Test parsing values with special characters."""
        with patch.dict(os.environ, {"TEST_VAR": "X-Header=@value-with_special.chars"}):
            headers = parse_extra_headers("TEST_VAR")
            assert headers == {"X-Header": "@value-with_special.chars"}

    def test_multiple_commas_in_value(self):
        """Test that commas in values are not supported (limitation of format)."""
        # This is a known limitation - values cannot contain commas
        with patch.dict(os.environ, {"TEST_VAR": "X-Header=val1,val2"}):
            headers = parse_extra_headers("TEST_VAR")
            # This will parse as two headers, second one invalid
            # Only X-Header=val1 is valid
            assert "X-Header" in headers


class TestConfigVariables:
    """Test that config variables are properly initialized."""

    def test_tts_extra_headers_default(self):
        """Test TTS_EXTRA_HEADERS defaults to empty dict."""
        from voice_mode import config
        # Default should be empty dict when env var not set
        if "VOICEMODE_TTS_EXTRA_HEADERS" not in os.environ:
            assert config.TTS_EXTRA_HEADERS == {}

    def test_stt_extra_headers_default(self):
        """Test STT_EXTRA_HEADERS defaults to empty dict."""
        from voice_mode import config
        # Default should be empty dict when env var not set
        if "VOICEMODE_STT_EXTRA_HEADERS" not in os.environ:
            assert config.STT_EXTRA_HEADERS == {}

    def test_headers_from_environment(self):
        """Test that headers are loaded from environment variables."""
        import importlib
        with patch.dict(os.environ, {
            "VOICEMODE_TTS_EXTRA_HEADERS": "X-TTS=test",
            "VOICEMODE_STT_EXTRA_HEADERS": "X-STT=test"
        }):
            # Reload config to pick up new env vars
            from voice_mode import config
            importlib.reload(config)

            assert config.TTS_EXTRA_HEADERS == {"X-TTS": "test"}
            assert config.STT_EXTRA_HEADERS == {"X-STT": "test"}


class TestClientInstantiation:
    """Test that headers are passed to AsyncOpenAI clients."""

    @pytest.mark.asyncio
    async def test_core_get_openai_clients_with_headers(self):
        """Test get_openai_clients passes headers correctly."""
        from voice_mode.core import get_openai_clients
        from unittest.mock import AsyncMock

        with patch.dict(os.environ, {
            "VOICEMODE_TTS_EXTRA_HEADERS": "X-TTS=test",
            "VOICEMODE_STT_EXTRA_HEADERS": "X-STT=test"
        }):
            # Reload config to pick up new env vars
            import importlib
            from voice_mode import config
            importlib.reload(config)

            with patch('voice_mode.core.AsyncOpenAI') as mock_openai_class:
                mock_client = AsyncMock()
                mock_openai_class.return_value = mock_client

                clients = get_openai_clients(
                    api_key="test-key",
                    stt_base_url="http://test-stt",
                    tts_base_url="http://test-tts"
                )

                # Verify AsyncOpenAI was called twice
                assert mock_openai_class.call_count == 2

                # Get all calls
                calls = mock_openai_class.call_args_list

                # Find STT and TTS calls
                stt_call = None
                tts_call = None
                for call in calls:
                    if call.kwargs.get('base_url') == 'http://test-stt':
                        stt_call = call
                    elif call.kwargs.get('base_url') == 'http://test-tts':
                        tts_call = call

                # Verify headers were passed
                assert stt_call is not None
                assert tts_call is not None
                assert stt_call.kwargs.get('default_headers') == {"X-STT": "test"}
                assert tts_call.kwargs.get('default_headers') == {"X-TTS": "test"}

    def test_headers_none_when_empty(self):
        """Test that None is passed when headers are empty."""
        from voice_mode.core import get_openai_clients
        from unittest.mock import AsyncMock

        with patch.dict(os.environ, {}, clear=True):
            # Reload config to clear headers
            import importlib
            from voice_mode import config
            importlib.reload(config)

            with patch('voice_mode.core.AsyncOpenAI') as mock_openai_class:
                mock_client = AsyncMock()
                mock_openai_class.return_value = mock_client

                clients = get_openai_clients(
                    api_key="test-key",
                    stt_base_url="http://test-stt",
                    tts_base_url="http://test-tts"
                )

                # Verify AsyncOpenAI was called with None or empty dict for default_headers
                calls = mock_openai_class.call_args_list
                for call in calls:
                    headers = call.kwargs.get('default_headers')
                    # Should be None or empty dict
                    assert headers is None or headers == {}
