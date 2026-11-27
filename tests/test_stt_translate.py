"""Tests for VOICEMODE_STT_TRANSLATE -- the /audio/translations endpoint (#240).

With ``VOICEMODE_STT_TRANSLATE=true``, ``simple_stt_failover`` calls
``client.audio.translations.create`` instead of
``client.audio.transcriptions.create``: the OpenAI-compatible translations
endpoint answers in English whatever language was spoken (Whisper's
translate-to-English task).

That API has no ``language`` parameter -- the source language is auto-detected
-- so ``WHISPER_LANGUAGE`` is never sent while translate is on, whatever it is
set to. Failure classification, the local transient-retry loop and endpoint
failover are unchanged; the recorded endpoint just names the path that was
called.

NOTE: ``simple_failover`` binds STT_BASE_URLS / STT_TRANSLATE / WHISPER_LANGUAGE
/ STT_PROMPT at import time, so tests patch the names on
``voice_mode.simple_failover``.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openai import APIStatusError

from voice_mode.simple_failover import simple_stt_failover

WHISPER_CPP = ["http://127.0.0.1:2022/v1"]
TWO_LOCAL = ["http://127.0.0.1:2022/v1", "http://127.0.0.1:8000/v1"]
REMOTE_ONLY = ["https://api.openai.com/v1"]


def _status_error(status_code, message="error"):
    response = MagicMock()
    response.status_code = status_code
    response.headers = MagicMock()
    response.headers.get = MagicMock(return_value=None)
    return APIStatusError(message, response=response, body=None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make backoff instantaneous so retries don't slow the suite."""
    async def _instant(_delay):
        return None
    monkeypatch.setattr("voice_mode.simple_failover.asyncio.sleep", _instant)


class TestTranslateOn:
    """STT_TRANSLATE=true routes the request to /audio/translations."""

    @pytest.mark.asyncio
    async def test_calls_translations_not_transcriptions(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        translate = MockClient.return_value.audio.translations.create = AsyncMock(
                            return_value="Hello, this is a test."
                        )
                        transcribe = MockClient.return_value.audio.transcriptions.create = AsyncMock()
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hello, this is a test."
        assert result["provider"] == "whisper"
        translate.assert_called_once()
        transcribe.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("language", ["auto", "de", "el"])
    async def test_language_is_never_sent_whatever_the_setting(self, language):
        """The translations API has no `language` parameter -- passing one
        would raise (the SDK does not accept it) or be rejected, so the request
        must omit it even when the user configured an explicit language."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", language):
                with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        translate = MockClient.return_value.audio.translations.create = AsyncMock(
                            return_value="Hello."
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hello."
        assert "language" not in translate.call_args.kwargs

    @pytest.mark.asyncio
    async def test_stt_prompt_is_still_sent(self):
        """Vocabulary biasing works on translations too (the API takes
        `prompt`), so the configured prompt must still go out."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                with patch("voice_mode.simple_failover.STT_PROMPT", "Yassou, VoiceMode"):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        translate = MockClient.return_value.audio.translations.create = AsyncMock(
                            return_value="Hello."
                        )
                        await simple_stt_failover(mock_file)

        assert translate.call_args.kwargs["prompt"] == "Yassou, VoiceMode"

    @pytest.mark.asyncio
    async def test_model_and_response_format_still_sent(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", REMOTE_ONLY):
            with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                with patch("voice_mode.simple_failover.OPENAI_API_KEY", "sk-test"):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        translate = MockClient.return_value.audio.translations.create = AsyncMock(
                            return_value="Hello."
                        )
                        await simple_stt_failover(mock_file)

        assert translate.call_args.kwargs["model"] == "whisper-1"
        assert translate.call_args.kwargs["response_format"] == "text"

    @pytest.mark.asyncio
    async def test_failure_records_the_translations_endpoint(self):
        """Error reporting must name the path that was actually called."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        MockClient.return_value.audio.translations.create = AsyncMock(
                            side_effect=_status_error(404, "Not Found")
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "model_not_found"
        assert result["endpoint"] == f"{WHISPER_CPP[0]}/audio/translations"
        assert result["attempted_endpoints"][0]["endpoint"] == (
            f"{WHISPER_CPP[0]}/audio/translations"
        )

    @pytest.mark.asyncio
    async def test_transient_failure_still_retries_on_translations(self):
        """The local transient-retry loop (VM-926) is endpoint-agnostic: a 500
        that clears on retry succeeds without failing over."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 2):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        translate = MockClient.return_value.audio.translations.create = AsyncMock(
                            side_effect=[_status_error(500), "Hello."]
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hello."
        assert translate.call_count == 2

    @pytest.mark.asyncio
    async def test_failover_to_next_endpoint_uses_translations_too(self):
        """When the primary endpoint fails, the fallback endpoint is asked to
        translate as well -- every chain entry gets the same request shape."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", TWO_LOCAL):
            with patch("voice_mode.simple_failover.STT_TRANSLATE", True):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        translate = MockClient.return_value.audio.translations.create = AsyncMock(
                            side_effect=[Exception("connection refused"), "Hello."]
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hello."
        assert result["endpoint"] == TWO_LOCAL[1]
        assert translate.call_count == 2


class TestTranslateOff:
    """STT_TRANSLATE=false (the default) leaves transcription untouched."""

    @pytest.mark.asyncio
    async def test_transcriptions_endpoint_used_by_default(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.STT_TRANSLATE", False):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        transcribe = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            return_value="Γεια σου."
                        )
                        translate = MockClient.return_value.audio.translations.create = AsyncMock()
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Γεια σου."
        transcribe.assert_called_once()
        translate.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_records_the_transcriptions_endpoint(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.STT_TRANSLATE", False):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            side_effect=_status_error(404, "Not Found")
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "model_not_found"
        assert result["endpoint"] == f"{WHISPER_CPP[0]}/audio/transcriptions"
