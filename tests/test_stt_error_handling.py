"""Tests for STT error handling and connection failure detection"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from openai import NotFoundError, AuthenticationError, APIConnectionError, OpenAIError
from httpx import Response, Request
import tempfile

from voice_mode.simple_failover import simple_stt_failover


class TestSTTErrorHandling:
    """Test STT error handling and structured response generation"""

    @pytest.mark.asyncio
    async def test_connection_refused_all_endpoints(self):
        """Test when all endpoints fail with connection errors"""
        # Mock file object
        mock_file = MagicMock()

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

            assert result["error_type"] == "connection_failed"
            assert len(result["attempted_endpoints"]) == 2

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

            assert result["error_type"] == "connection_failed"
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