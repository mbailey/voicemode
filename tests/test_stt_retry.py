"""Regression tests for VM-926: transient-retry for local STT.

Local whisper.cpp times out transiently a few times a day; before this fix the
STT client was built with ``max_retries=0`` for local providers and the failover
loop made a single transcription attempt, so a transient timeout on the sole
local endpoint hard-failed the voice turn. ``simple_stt_failover`` now wraps the
per-endpoint transcription call in a bounded, transient-only retry loop with
exponential backoff (config: ``VOICEMODE_STT_RETRY_ATTEMPTS`` /
``VOICEMODE_STT_RETRY_BACKOFF`` / ``VOICEMODE_STT_RETRY_BACKOFF_MAX``).

These tests pin STT_BASE_URLS to a SINGLE local endpoint so that a *retry*
(not an endpoint failover) is the only thing that can recover the turn — the
distinction the fix is about. ``asyncio.sleep`` is patched to a no-op so the
backoff doesn't slow the suite.

NOTE: ``simple_failover`` binds STT_BASE_URLS / STT_RETRY_* at import time
(``from .config import ...``), so tests patch the names on the
``voice_mode.simple_failover`` module, not on ``voice_mode.config``.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openai import (
    APITimeoutError,
    APIConnectionError,
    APIStatusError,
    BadRequestError,
    RateLimitError,
)

from voice_mode.simple_failover import simple_stt_failover, _is_transient_stt_error

# Single LOCAL endpoint: the whisper.cpp-only host in the bug report. With one
# endpoint there is nothing to fail over to, so retry is the sole recovery path.
LOCAL_ONLY = ["http://127.0.0.1:2022/v1"]
# Single REMOTE endpoint, for the no-regression guard.
REMOTE_ONLY = ["https://api.openai.com/v1"]


def _timeout_error():
    return APITimeoutError(request=MagicMock())


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


class TestIsTransientSTTError:
    """Unit-test the transient/permanent classifier directly."""

    def test_timeout_is_transient(self):
        assert _is_transient_stt_error(_timeout_error()) is True

    def test_connection_error_is_transient(self):
        assert _is_transient_stt_error(
            APIConnectionError(message="connection reset", request=MagicMock())
        ) is True

    def test_5xx_is_transient(self):
        assert _is_transient_stt_error(_status_error(503)) is True

    def test_500_boundary_is_transient(self):
        assert _is_transient_stt_error(_status_error(500)) is True

    def test_4xx_is_permanent(self):
        # 400 bad audio / 401 auth / 404 wrong path / 422 unprocessable
        for code in (400, 401, 403, 404, 422):
            assert _is_transient_stt_error(_status_error(code)) is False

    def test_429_rate_limit_is_permanent(self):
        # super.voicemode locked 429 as PERMANENT for local (design §4 / §9).
        response = MagicMock()
        response.status_code = 429
        response.headers = MagicMock()
        response.headers.get = MagicMock(return_value=None)
        rate_limit = RateLimitError(message="rate", response=response, body=None)
        assert _is_transient_stt_error(rate_limit) is False

    def test_unknown_exception_is_permanent(self):
        # Fail closed: never loop on an error type we don't understand.
        assert _is_transient_stt_error(ValueError("boom")) is False


class TestLocalSTTRetry:
    """End-to-end behaviour of the retry loop through simple_stt_failover."""

    @pytest.mark.asyncio
    async def test_transient_timeout_is_retried_and_succeeds(self):
        """The core bug: a single transient timeout on the lone local endpoint
        must be retried and recover, instead of losing the turn."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", LOCAL_ONLY):
            with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                mock_client = MockClient.return_value
                mock_client.audio.transcriptions.create = AsyncMock(
                    side_effect=[_timeout_error(), "Hello, this is a test."]
                )

                result = await simple_stt_failover(mock_file)

        assert result["text"] == "Hello, this is a test."
        assert result["provider"] == "whisper"
        assert "error_type" not in result
        # Retried exactly once after the initial failure = 2 total attempts.
        assert mock_client.audio.transcriptions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_permanent_error_is_not_retried(self):
        """A permanent error (400 bad audio) must NOT be retried — a single
        attempt, then the turn fails."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", LOCAL_ONLY):
            with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                mock_client = MockClient.return_value
                mock_client.audio.transcriptions.create = AsyncMock(
                    side_effect=BadRequestError(
                        message="bad audio",
                        response=_status_error(400).response,
                        body=None,
                    )
                )

                result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert mock_client.audio.transcriptions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limit_is_not_retried(self):
        """429 is PERMANENT for local (design §9): no retry."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", LOCAL_ONLY):
            with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                mock_client = MockClient.return_value
                mock_client.audio.transcriptions.create = AsyncMock(
                    side_effect=RateLimitError(
                        message="rate",
                        response=_status_error(429).response,
                        body=None,
                    )
                )

                result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert mock_client.audio.transcriptions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_attempts_config_is_honoured(self):
        """VOICEMODE_STT_RETRY_ATTEMPTS=1 → exactly 2 total tries, then the
        turn fails (retries exhausted re-raise → connection_failed)."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", LOCAL_ONLY):
            with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 1):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    mock_client = MockClient.return_value
                    # Always times out — never recovers.
                    mock_client.audio.transcriptions.create = AsyncMock(
                        side_effect=_timeout_error()
                    )

                    result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        # 1 initial + 1 retry = 2, and no more.
        assert mock_client.audio.transcriptions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_disabled_when_attempts_zero(self):
        """VOICEMODE_STT_RETRY_ATTEMPTS=0 disables the loop for local: a
        transient timeout is a single attempt (opt-out preserves old behaviour)."""
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", LOCAL_ONLY):
            with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 0):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    mock_client = MockClient.return_value
                    mock_client.audio.transcriptions.create = AsyncMock(
                        side_effect=[_timeout_error(), "recovered"]
                    )

                    result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert mock_client.audio.transcriptions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_backoff_delays_are_exponential_and_capped(self):
        """VOICEMODE_STT_RETRY_BACKOFF / _BACKOFF_MAX honour env (README
        "backoff honours voicemode.env"): successive backoff sleeps follow
        ``min(base * 2**attempt, cap)``. With base=0.5, cap=4.0 the sequence
        is 0.5, 1.0, 2.0, 4.0, then clamped at 4.0 (0.5*2**4 = 8.0 -> capped).
        The other tests no-op ``asyncio.sleep`` and so never assert the delay
        value or that the cap engages; this one records the delays."""
        mock_file = MagicMock()
        delays = []

        async def _record(delay):
            delays.append(delay)

        with patch("voice_mode.simple_failover.STT_BASE_URLS", LOCAL_ONLY):
            with patch("voice_mode.simple_failover.STT_RETRY_ATTEMPTS", 5):
                with patch("voice_mode.simple_failover.STT_RETRY_BACKOFF", 0.5):
                    with patch("voice_mode.simple_failover.STT_RETRY_BACKOFF_MAX", 4.0):
                        # Override the autouse no-op sleep with a recorder.
                        with patch("voice_mode.simple_failover.asyncio.sleep", _record):
                            with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                                mock_client = MockClient.return_value
                                # Always times out — never recovers, so all
                                # retries fire and we see the full delay series.
                                mock_client.audio.transcriptions.create = AsyncMock(
                                    side_effect=_timeout_error()
                                )

                                result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        # 1 initial + 5 retries = 6 attempts, so 5 backoff sleeps between them.
        assert mock_client.audio.transcriptions.create.call_count == 6
        # Exponential 0.5, 1.0, 2.0, 4.0 then clamped at the 4.0 cap.
        assert delays == [0.5, 1.0, 2.0, 4.0, 4.0]


class TestRemoteRegressionGuard:
    """Remote endpoints must NOT gain retries from our loop (they keep the
    OpenAI SDK's own max_retries=2 at the client level, which is mocked out
    here — so from the loop's perspective a remote transient error is a single
    attempt)."""

    @pytest.mark.asyncio
    async def test_remote_endpoint_not_retried_by_loop(self):
        mock_file = MagicMock()

        with patch("voice_mode.simple_failover.STT_BASE_URLS", REMOTE_ONLY):
            with patch("voice_mode.simple_failover.OPENAI_API_KEY", "sk-test"):
                with patch("voice_mode.simple_failover.AsyncOpenAI") as MockClient:
                    mock_client = MockClient.return_value
                    # Would succeed on a retry — but our loop must not retry remote.
                    mock_client.audio.transcriptions.create = AsyncMock(
                        side_effect=[_timeout_error(), "would-have-recovered"]
                    )

                    result = await simple_stt_failover(mock_file)

        assert result["error_type"] == "connection_failed"
        assert mock_client.audio.transcriptions.create.call_count == 1
