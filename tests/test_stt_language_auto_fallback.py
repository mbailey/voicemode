"""Tests for language="auto" on local STT endpoints that are not whisper.cpp.

With the default ``VOICEMODE_WHISPER_LANGUAGE=auto``, ``simple_stt_failover``
sends ``language="auto"`` to every local endpoint, because whisper.cpp defaults
to English unless told otherwise. Other OpenAI-compatible servers reject that
value: speaches (faster-whisper) answers HTTP 500, and auto-detects correctly
when ``language`` is simply omitted. Before this fix every request to such a
server failed under default settings.

The fix keeps sending "auto" first, and only when an implicit "auto" request
still fails with a 5xx after the transient retries does it try once more
without ``language``. An endpoint where that works is remembered, so later
requests omit ``language`` straight away.

The server mocks below mirror what speaches did on one machine with one test
recording: 500 for ``language="auto"``, success without it.

NOTE: ``simple_failover`` binds STT_BASE_URLS / WHISPER_LANGUAGE at import time,
so tests patch the names on ``voice_mode.simple_failover``.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openai import APIStatusError

import voice_mode.simple_failover as simple_failover
from voice_mode.simple_failover import simple_stt_failover

WHISPER_CPP = ["http://127.0.0.1:2022/v1"]
# A local OpenAI-compatible server on a port voicemode does not know about.
SPEACHES = ["http://127.0.0.1:8000/v1"]
REMOTE_ONLY = ["https://api.openai.com/v1"]


def _status_error(status_code, message="error"):
    response = MagicMock()
    response.status_code = status_code
    response.headers = MagicMock()
    response.headers.get = MagicMock(return_value=None)
    return APIStatusError(message, response=response, body=None)


def _speaches_like(**kwargs):
    """500 when language="auto" is sent, a transcription otherwise."""
    if kwargs.get("language") == "auto":
        raise _status_error(500, "Internal Server Error")
    return "Hallo, das ist ein Test."


def _languages_sent(create_mock):
    return [call.kwargs.get("language", "<omitted>") for call in create_mock.call_args_list]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make backoff instantaneous so retries don't slow the suite."""
    async def _instant(_delay):
        return None
    monkeypatch.setattr("voice_mode.simple_failover.asyncio.sleep", _instant)


@pytest.fixture(autouse=True)
def fresh_endpoint_memory(monkeypatch):
    """The remembered endpoints are process-global; isolate each test."""
    monkeypatch.setattr(simple_failover, "_STT_ENDPOINTS_REJECTING_AUTO_LANGUAGE", set())


class TestWhisperCppUnchanged:

    @pytest.mark.asyncio
    async def test_whisper_cpp_still_gets_auto_with_no_extra_request(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                        return_value="Hello."
                    )
                    result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hello."
        assert _languages_sent(create) == ["auto"]

    @pytest.mark.asyncio
    async def test_transient_500_that_clears_keeps_auto(self):
        """A 500 that clears on the normal retry must not drop "auto": the
        fallback only runs once the retries are exhausted."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                        side_effect=[_status_error(500), "Hello.", "Again."]
                    )
                    first = await simple_stt_failover(mock_file)
                    second = await simple_stt_failover(mock_file)

        assert first["text"] == "Hello."
        assert second["text"] == "Again."
        assert _languages_sent(create) == ["auto", "auto", "auto"]

    @pytest.mark.asyncio
    async def test_real_failure_is_reported_and_not_remembered(self):
        """If the request fails without language too, the error was not about
        language: the turn fails as before and nothing is remembered."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            side_effect=_status_error(500, "model crashed")
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert "model crashed" in result["attempted_endpoints"][0]["error"]
        assert _languages_sent(create) == ["auto", "<omitted>"]
        assert simple_failover._STT_ENDPOINTS_REJECTING_AUTO_LANGUAGE == set()

    @pytest.mark.asyncio
    async def test_4xx_does_not_trigger_the_fallback(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                        side_effect=_status_error(400, "bad audio")
                    )
                    result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert _languages_sent(create) == ["auto"]


class TestServerRejectingAuto:

    @pytest.mark.asyncio
    async def test_default_settings_transcribe_successfully(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", SPEACHES):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 2):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            side_effect=_speaches_like
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hallo, das ist ein Test."
        assert result["endpoint"] == SPEACHES[0]
        # 1 try + 2 transient retries with "auto", then one without.
        assert _languages_sent(create) == ["auto", "auto", "auto", "<omitted>"]

    @pytest.mark.asyncio
    async def test_endpoint_is_remembered_so_later_calls_skip_auto(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", SPEACHES):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            side_effect=_speaches_like
                        )
                        await simple_stt_failover(mock_file)
                        create.reset_mock()
                        result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hallo, das ist ein Test."
        assert _languages_sent(create) == ["<omitted>"]

    @pytest.mark.asyncio
    async def test_memory_is_per_endpoint(self):
        """Learning that one endpoint rejects "auto" must not change what a
        whisper.cpp endpoint is sent."""
        mock_file = MagicMock()
        simple_failover._STT_ENDPOINTS_REJECTING_AUTO_LANGUAGE.add(SPEACHES[0])

        with patch("voice_mode.simple_failover.STT_BASE_URLS", WHISPER_CPP):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                        return_value="Hello."
                    )
                    await simple_stt_failover(mock_file)

        assert _languages_sent(create) == ["auto"]


class TestOtherLanguageSettingsUnchanged:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("urls", [WHISPER_CPP, SPEACHES, REMOTE_ONLY])
    async def test_explicit_language_is_passed_to_every_provider(self, urls):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", urls):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "de"):
                with patch("voice_mode.simple_failover.OPENAI_API_KEY", "sk-test"):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            return_value="Hallo."
                        )
                        await simple_stt_failover(mock_file)

        assert _languages_sent(create) == ["de"]

    @pytest.mark.asyncio
    async def test_explicit_language_failure_does_not_trigger_the_fallback(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", SPEACHES):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "de"):
                with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            side_effect=_status_error(500)
                        )
                        result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert _languages_sent(create) == ["de"]

    @pytest.mark.asyncio
    async def test_openai_still_omits_language(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", REMOTE_ONLY):
            with patch("voice_mode.simple_failover.WHISPER_LANGUAGE", "auto"):
                with patch("voice_mode.simple_failover.OPENAI_API_KEY", "sk-test"):
                    with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                        create = MockClient.return_value.audio.transcriptions.create = AsyncMock(
                            return_value="Hello."
                        )
                        await simple_stt_failover(mock_file)

        assert _languages_sent(create) == ["<omitted>"]
