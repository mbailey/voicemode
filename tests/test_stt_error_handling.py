"""Tests for STT error handling and connection failure detection"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from openai import NotFoundError, AuthenticationError, APIConnectionError, OpenAIError
from httpx import Response, Request
import tempfile

from voice_mode.simple_failover import simple_stt_failover

# Test config: use exactly 2 endpoints (local Whisper + OpenAI)
TEST_STT_BASE_URLS = ["http://127.0.0.1:2022/v1", "https://api.openai.com/v1"]


@pytest.fixture(autouse=True)
def pin_stt_base_urls(monkeypatch):
    """Pin simple_failover.STT_BASE_URLS to TEST_STT_BASE_URLS so tests are
    isolated from the user's ~/.voicemode/voicemode.env (which may put
    mlx-audio first or omit OpenAI entirely). See VM-1138.

    `simple_failover` does `from .config import STT_BASE_URLS` at module load,
    so it carries its own bound name — patch the failover module, not config.
    """
    monkeypatch.setattr("voice_mode.simple_failover.STT_BASE_URLS", list(TEST_STT_BASE_URLS))


@pytest.fixture(autouse=True)
def no_stt_backoff_sleep(monkeypatch):
    """Make the VM-926 local-STT retry backoff instantaneous in unit tests.

    ``simple_stt_failover`` now retries a LOCAL endpoint on transient failures
    (timeout / connection reset) with an exponential backoff sleep. The
    connection-error tests below exercise the local whisper endpoint, so without
    this they would incur real backoff sleeps. No-op the sleep to keep the suite
    fast; retry *behaviour* is asserted in test_stt_retry.py.
    """
    async def _instant(_delay):
        return None
    monkeypatch.setattr("voice_mode.simple_failover.asyncio.sleep", _instant)


class TestSTTErrorHandling:
    """Test STT error handling and structured response generation"""

    @pytest.mark.asyncio
    async def test_connection_refused_all_endpoints(self):
        """Test when all endpoints fail with connection errors"""
        # Mock file object
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.STT_BASE_URLS', TEST_STT_BASE_URLS):
            with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
                # Mock connection refused for both Whisper and OpenAI
                mock_client = MockClient.return_value
                mock_client.audio.transcriptions.create = AsyncMock(
                    side_effect=APIConnectionError(
                        message="Connection error.",
                        request=MagicMock()
                    )
                )

                result = await simple_stt_failover(mock_file)

                assert result is not None
                assert result["error_type"] == "connection_failed"
                assert "attempted_endpoints" in result
                assert len(result["attempted_endpoints"]) == 2  # Whisper and OpenAI

                # Check Whisper error
                whisper_attempt = result["attempted_endpoints"][0]
                assert "127.0.0.1:2022" in whisper_attempt["endpoint"]
                assert whisper_attempt["provider"] == "whisper"
                assert "Connection error" in whisper_attempt["error"]

    @pytest.mark.asyncio
    async def test_authentication_error_openai(self):
        """Test when OpenAI fails with authentication error"""
        mock_file = MagicMock()

        # This test is about failover surfacing OpenAI's auth error, not about
        # retry. Pin STT_RETRY_ATTEMPTS=0 so the local whisper connection error
        # is a single attempt that fails over immediately (VM-926 would otherwise
        # retry the transient local connection error and consume the second
        # side_effect below). Retry behaviour is covered in test_stt_retry.py.
        with patch('voice_mode.simple_failover.STT_RETRY_ATTEMPTS', 0):
            with patch('voice_mode.simple_failover.STT_BASE_URLS', TEST_STT_BASE_URLS):
                with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
                    mock_client = MockClient.return_value

                    # First call (Whisper) - connection refused
                    # Second call (OpenAI) - auth error
                    mock_client.audio.transcriptions.create = AsyncMock(
                        side_effect=[
                            APIConnectionError(message="Connection error.", request=MagicMock()),
                            AuthenticationError(
                                message="Error code: 401 - Incorrect API key provided",
                                response=MagicMock(status_code=401),
                                body={'error': {'message': 'Incorrect API key'}},
                            )
                        ]
                    )

                    result = await simple_stt_failover(mock_file)

                # VM-2342: OpenAI ANSWERED with 401, which outranks the local
                # connection error; it is not a connection failure.
                assert result["error_type"] == "request_rejected"
                assert result["status_code"] == 401
                assert len(result["attempted_endpoints"]) == 2
                assert result["attempted_endpoints"][0]["error_type"] == "connection_failed"
                assert result["attempted_endpoints"][1]["error_type"] == "request_rejected"

                # Check OpenAI error
                openai_attempt = result["attempted_endpoints"][1]
                assert openai_attempt["provider"] == "openai"
                assert "401" in openai_attempt["error"] or "Incorrect API key" in openai_attempt["error"]

    @pytest.mark.asyncio
    async def test_no_api_key_error(self):
        """Test when OPENAI_API_KEY is not set"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
            # Simulate the OpenAI client initialization error when no API key
            def raise_no_api_key(*args, **kwargs):
                if kwargs.get('api_key') == 'dummy-key-for-local':
                    return MockClient.return_value
                raise OpenAIError(
                    "The api_key client option must be set either by passing api_key to the client or by setting the OPENAI_API_KEY environment variable"
                )

            MockClient.side_effect = raise_no_api_key
            mock_client = MockClient.return_value
            mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=APIConnectionError(message="Connection error.", request=MagicMock())
            )

            with patch('voice_mode.simple_failover.OPENAI_API_KEY', None):
                result = await simple_stt_failover(mock_file)

            assert result["error_type"] == "connection_failed"

    @pytest.mark.asyncio
    async def test_wrong_endpoint_path(self):
        """Test when Whisper is on wrong endpoint path"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
            mock_client = MockClient.return_value

            # Simulate 404 error from wrong path
            mock_response = MagicMock(spec=Response)
            mock_response.status_code = 404
            mock_response.headers = MagicMock()
            mock_response.headers.get = MagicMock(return_value=None)
            mock_request = MagicMock(spec=Request)

            mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=NotFoundError(
                    message="File Not Found (/audio/transcriptions)",
                    response=mock_response,
                    body="File Not Found (/audio/transcriptions)",
                )
            )

            result = await simple_stt_failover(mock_file)

            # VM-2342: a 404 is the server answering, reported as
            # model_not_found (the converse message also names a wrong path).
            assert result["error_type"] == "model_not_found"
            assert result["status_code"] == 404
            whisper_attempt = result["attempted_endpoints"][0]
            assert "404" in whisper_attempt["error"] or "Not Found" in whisper_attempt["error"]

    @pytest.mark.asyncio
    async def test_successful_but_no_speech(self):
        """Test when STT connects successfully but detects no speech"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
            mock_client = MockClient.return_value

            # Return empty string (no speech detected)
            mock_client.audio.transcriptions.create = AsyncMock(
                return_value=""
            )

            result = await simple_stt_failover(mock_file)

            assert result["error_type"] == "no_speech"
            # Provider could be either whisper or openai depending on which succeeds
            assert result["provider"] in ["whisper", "openai"]

    @pytest.mark.asyncio
    async def test_whisper_error_as_json_text(self):
        """Test when Whisper returns error as JSON in text field"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
            mock_client = MockClient.return_value

            # Whisper returns error as JSON string in successful response
            mock_client.audio.transcriptions.create = AsyncMock(
                return_value='{"error":"failed to read audio data"}'
            )

            result = await simple_stt_failover(mock_file)

            # This is treated as successful transcription of the error message
            assert "text" in result
            assert result["text"] == '{"error":"failed to read audio data"}'
            assert result["provider"] == "whisper"

    @pytest.mark.asyncio
    async def test_successful_transcription(self):
        """Test successful transcription"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
            mock_client = MockClient.return_value

            # Successful transcription
            mock_client.audio.transcriptions.create = AsyncMock(
                return_value="Hello, this is a test transcription."
            )

            result = await simple_stt_failover(mock_file)

            assert "text" in result
            assert result["text"] == "Hello, this is a test transcription."
            assert result["provider"] == "whisper"
            assert "error_type" not in result

    @pytest.mark.asyncio
    async def test_fallback_to_openai(self):
        """Test fallback from Whisper to OpenAI"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.STT_BASE_URLS', TEST_STT_BASE_URLS):
            with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
                # Need to handle different clients for Whisper and OpenAI
                whisper_client = MagicMock()
                openai_client = MagicMock()

                # Track which client is being created
                call_count = 0

                def create_client(*args, **kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:  # First call is Whisper
                        whisper_client.audio.transcriptions.create = AsyncMock(
                            side_effect=APIConnectionError(
                                message="Connection error.",
                                request=MagicMock()
                            )
                        )
                        return whisper_client
                    else:  # Second call is OpenAI
                        openai_client.audio.transcriptions.create = AsyncMock(
                            return_value="Transcribed by OpenAI"
                        )
                        return openai_client

                MockClient.side_effect = create_client

                result = await simple_stt_failover(mock_file)

                assert "text" in result
                assert result["text"] == "Transcribed by OpenAI"
                assert result["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_mixed_results_prefer_successful(self):
        """Test that successful empty result is preferred over connection errors"""
        mock_file = MagicMock()

        with patch('voice_mode.simple_failover.AsyncOpenAI') as MockClient:
            whisper_client = MagicMock()
            openai_client = MagicMock()

            call_count = 0

            def create_client(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # Whisper fails
                    whisper_client.audio.transcriptions.create = AsyncMock(
                        side_effect=APIConnectionError(
                            message="Connection error.",
                            request=MagicMock()
                        )
                    )
                    return whisper_client
                else:  # OpenAI succeeds but returns empty
                    openai_client.audio.transcriptions.create = AsyncMock(
                        return_value=""
                    )
                    return openai_client

            MockClient.side_effect = create_client

            result = await simple_stt_failover(mock_file)

            # Should report no_speech, not connection_failed
            assert result["error_type"] == "no_speech"
            assert result["provider"] == "openai"

# ---------------------------------------------------------------------------
# VM-2342: an HTTP 4xx is the server ANSWERING. It must be reported as what it
# is (model_not_found for 404), never as connection_failed.
# ---------------------------------------------------------------------------

from openai import APIStatusError, BadRequestError, InternalServerError  # noqa: E402
import httpx  # noqa: E402

from voice_mode.simple_failover import _classify_stt_failure  # noqa: E402

MLX_URL = "http://127.0.0.1:8890/v1"
CPP_URL = "http://127.0.0.1:2022/v1"


def _http_error(cls, status, url=MLX_URL, body="Not Found"):
    """A real openai status error carrying a real httpx response."""
    request = httpx.Request("POST", f"{url}/audio/transcriptions")
    response = httpx.Response(status, request=request)
    return cls(message=f"Error code: {status} - {body}", response=response, body=body)


def _conn_error():
    return APIConnectionError(message="Connection error.", request=MagicMock())


async def _run_chain(urls, per_endpoint_effects, stt_models=None):
    """Run simple_stt_failover over ``urls``; endpoint i raises/returns
    ``per_endpoint_effects[i]``. Retries are off so each endpoint is tried once."""
    clients = []
    for effect in per_endpoint_effects:
        client = MagicMock()
        if isinstance(effect, Exception):
            client.audio.transcriptions.create = AsyncMock(side_effect=effect)
        else:
            client.audio.transcriptions.create = AsyncMock(return_value=effect)
        clients.append(client)
    clients_iter = iter(clients)

    with patch("voice_mode.simple_failover.STT_BASE_URLS", list(urls)), \
         patch("voice_mode.providers.STT_BASE_URLS", list(urls)), \
         patch("voice_mode.providers.STT_MODELS", list(stt_models or [])), \
         patch("voice_mode.providers.STT_MODEL", "whisper-1"), \
         patch("voice_mode.providers.STT_MODEL_EXPLICIT", True), \
         patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0), \
         patch("voice_mode.simple_failover.AsyncOpenAI", side_effect=lambda **_k: next(clients_iter)):
        return await simple_stt_failover(MagicMock())


class TestSTTHttpAnswerClassification:
    """VM-2342 regression tests: the bug was a 404 surfacing as connection_failed."""

    @pytest.mark.asyncio
    async def test_mlx_audio_404_is_model_not_found_naming_model_and_endpoint(self):
        """The measured bug: mlx-audio 0.5.7 404s on model 'whisper-1'."""
        result = await _run_chain([MLX_URL], [_http_error(NotFoundError, 404)])

        assert result["error_type"] == "model_not_found"
        assert result["error_type"] != "connection_failed"
        assert result["model"] == "whisper-1"
        assert result["endpoint"] == f"{MLX_URL}/audio/transcriptions"
        assert result["status_code"] == 404
        attempt = result["attempted_endpoints"][0]
        assert attempt["error_type"] == "model_not_found"
        assert attempt["model"] == "whisper-1"
        assert attempt["status_code"] == 404
        assert attempt["provider"] == "mlx-audio"

    @pytest.mark.asyncio
    async def test_404_names_the_model_actually_sent_per_endpoint(self):
        """A positional VOICEMODE_STT_MODELS entry is what was sent, so it is
        what the report names."""
        result = await _run_chain(
            [MLX_URL], [_http_error(NotFoundError, 404)], stt_models=["org/not-loaded"]
        )
        assert result["error_type"] == "model_not_found"
        assert result["model"] == "org/not-loaded"

    @pytest.mark.asyncio
    async def test_mixed_chain_refused_then_404_reports_model_not_found(self):
        """Mixed-chain rule: a server's 4xx answer outranks a connection error."""
        result = await _run_chain(
            [CPP_URL, MLX_URL], [_conn_error(), _http_error(NotFoundError, 404)]
        )
        assert result["error_type"] == "model_not_found"
        assert result["endpoint"] == f"{MLX_URL}/audio/transcriptions"
        kinds = [a["error_type"] for a in result["attempted_endpoints"]]
        assert kinds == ["connection_failed", "model_not_found"]

    @pytest.mark.asyncio
    async def test_mixed_chain_404_then_refused_reports_model_not_found(self):
        result = await _run_chain(
            [MLX_URL, CPP_URL], [_http_error(NotFoundError, 404), _conn_error()]
        )
        assert result["error_type"] == "model_not_found"
        assert result["endpoint"] == f"{MLX_URL}/audio/transcriptions"

    @pytest.mark.asyncio
    async def test_404_outranks_other_4xx(self):
        result = await _run_chain(
            [CPP_URL, MLX_URL],
            [_http_error(BadRequestError, 400, url=CPP_URL, body="bad audio"),
             _http_error(NotFoundError, 404)],
        )
        assert result["error_type"] == "model_not_found"
        assert result["endpoint"] == f"{MLX_URL}/audio/transcriptions"

    @pytest.mark.asyncio
    async def test_other_4xx_is_request_rejected(self):
        result = await _run_chain(
            [CPP_URL], [_http_error(BadRequestError, 400, url=CPP_URL, body="bad audio")]
        )
        assert result["error_type"] == "request_rejected"
        assert result["status_code"] == 400
        assert result["endpoint"] == f"{CPP_URL}/audio/transcriptions"

    @pytest.mark.asyncio
    async def test_5xx_stays_connection_failed(self):
        """Boundary: only 4xx is reclassified; a 5xx keeps today's behaviour."""
        result = await _run_chain(
            [MLX_URL], [_http_error(InternalServerError, 500, body="Processor not found")]
        )
        assert result["error_type"] == "connection_failed"
        assert result["attempted_endpoints"][0]["status_code"] == 500
        assert "model" not in result

    @pytest.mark.asyncio
    async def test_pure_connection_errors_unchanged(self):
        result = await _run_chain([CPP_URL, MLX_URL], [_conn_error(), _conn_error()])
        assert result["error_type"] == "connection_failed"
        assert set(result) == {"error_type", "attempted_endpoints"}
        for attempt in result["attempted_endpoints"]:
            assert attempt["error_type"] == "connection_failed"
            assert attempt["status_code"] is None

    @pytest.mark.asyncio
    async def test_success_after_404_still_wins(self):
        result = await _run_chain(
            [MLX_URL, CPP_URL], [_http_error(NotFoundError, 404), "hello"]
        )
        assert result["text"] == "hello"
        assert "error_type" not in result


class TestClassifySttFailure:
    def test_404(self):
        assert _classify_stt_failure(_http_error(NotFoundError, 404)) == (404, "model_not_found")

    def test_other_4xx(self):
        for status in (400, 401, 403, 422, 429):
            err = _http_error(APIStatusError, status)
            assert _classify_stt_failure(err) == (status, "request_rejected")

    def test_5xx(self):
        assert _classify_stt_failure(_http_error(InternalServerError, 503)) == (503, "connection_failed")

    def test_connection_and_unknown_errors(self):
        assert _classify_stt_failure(_conn_error()) == (None, "connection_failed")
        assert _classify_stt_failure(RuntimeError("boom")) == (None, "connection_failed")
