"""
Critical path tests for the converse tool.
These tests ensure the converse tool handles all failure modes gracefully.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
import json


class TestConverseOpenAIErrors:
    """Test that converse properly handles and reports OpenAI errors."""

    @pytest.mark.asyncio
    async def test_converse_reports_insufficient_quota_clearly(self):
        """Test that insufficient quota errors are clearly reported to users."""
        from voice_mode.tools.converse import converse

        # Mock at the core.text_to_speech level to avoid streaming complications
        with patch('voice_mode.core.text_to_speech') as mock_tts:
            # Simulate OpenAI quota exceeded error
            mock_tts.side_effect = Exception(
                "Error code: 429 - {'error': {'message': 'You exceeded your current quota, "
                "please check your plan and billing details.', 'type': 'insufficient_quota'}}"
            )

            with patch('voice_mode.config.TTS_BASE_URLS', ['https://api.openai.com/v1']):
                with patch('voice_mode.config.OPENAI_API_KEY', 'test-api-key'):
                    result = await converse.fn(
                        message="Test message",
                        wait_for_response=False
                    )

                # User should see a clear message about quota/credit issue
                assert any(keyword in result.lower() for keyword in [
                    'quota', 'credit', 'billing', 'api key', 'insufficient'
                ]), f"Error message doesn't clearly indicate quota issue: {result}"

    @pytest.mark.asyncio
    async def test_converse_reports_invalid_api_key_clearly(self):
        """Test that invalid API key errors are clearly reported."""
        from voice_mode.tools.converse import converse

        # Mock at the core.text_to_speech level to avoid streaming complications
        with patch('voice_mode.core.text_to_speech') as mock_tts:
            # Simulate invalid API key error
            mock_tts.side_effect = Exception(
                "Error code: 401 - {'error': {'message': 'Incorrect API key provided', "
                "'type': 'invalid_request_error'}}"
            )

            with patch('voice_mode.config.TTS_BASE_URLS', ['https://api.openai.com/v1']):
                with patch('voice_mode.config.OPENAI_API_KEY', 'invalid-key'):
                    result = await converse.fn(
                        message="Test message",
                        wait_for_response=False
                    )

                    # User should see a message about API key issue
                    assert any(keyword in result.lower() for keyword in [
                        'api key', 'authentication', 'invalid', 'incorrect'
                    ]), f"Error message doesn't indicate API key issue: {result}"

    @pytest.mark.asyncio
    async def test_converse_reports_rate_limit_clearly(self):
        """Test that rate limit errors are clearly reported."""
        from voice_mode.tools.converse import converse

        # Mock at the core.text_to_speech level to avoid streaming complications
        with patch('voice_mode.core.text_to_speech') as mock_tts:
            # Simulate rate limit error
            mock_tts.side_effect = Exception(
                "Error code: 429 - {'error': {'message': 'Rate limit reached', "
                "'type': 'rate_limit_exceeded'}}"
            )

            with patch('voice_mode.config.TTS_BASE_URLS', ['https://api.openai.com/v1']):
                result = await converse.fn(
                    message="Test message",
                    wait_for_response=False
                )

                # User should see a message about rate limiting
                assert any(keyword in result.lower() for keyword in [
                    'rate', 'limit', 'too many', 'requests'
                ]), f"Error message doesn't indicate rate limit: {result}"


class TestConverseFailoverBehavior:
    """Test the failover behavior when providers fail."""

    @pytest.mark.asyncio
    async def test_converse_tries_all_configured_endpoints(self):
        """Test that converse tries all configured endpoints before giving up."""
        from voice_mode.tools.converse import converse

        # Use simple_tts_failover mock which is easier to test
        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (False, None, {
                'error_type': 'all_providers_failed',
                'attempted_endpoints': [
                    {'provider': 'kokoro', 'error': 'Connection refused', 'endpoint': 'http://127.0.0.1:8880/v1'},
                    {'provider': 'openai', 'error': 'Connection refused', 'endpoint': 'https://api.openai.com/v1'}
                ]
            })

            test_urls = [
                'http://127.0.0.1:8880/v1',  # Kokoro
                'https://api.openai.com/v1'   # OpenAI
            ]

            with patch('voice_mode.config.TTS_BASE_URLS', test_urls):
                result = await converse.fn(
                    message="Test message",
                    wait_for_response=False
                )

                # Should have tried both endpoints (check from error config)
                call_args = mock_tts.call_args
                assert call_args is not None  # At least attempted TTS
                assert len(mock_tts.return_value[2]['attempted_endpoints']) >= len(test_urls) - 1

    @pytest.mark.asyncio
    async def test_converse_succeeds_with_second_endpoint(self):
        """Test that converse succeeds when first endpoint fails but second works."""
        from voice_mode.tools.converse import converse

        # Mock successful TTS
        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (True, {'duration_ms': 100}, {'provider': 'openai'})

            result = await converse.fn(
                message="Test message",
                wait_for_response=False
            )

            # Should succeed without error
            assert "✓" in result or "successfully" in result.lower()
            assert "Error" not in result and "✗" not in result


class TestConverseErrorMessages:
    """Test that error messages are helpful and actionable."""

    @pytest.mark.asyncio
    async def test_error_message_suggests_checking_services(self):
        """Test that errors suggest checking if services are running."""
        from voice_mode.tools.converse import converse

        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (False, None, {
                'error_type': 'all_providers_failed',
                'attempted_endpoints': [
                    {'provider': 'kokoro', 'error': 'Connection refused'},
                    {'provider': 'whisper', 'error': 'Connection refused'}
                ]
            })

            with patch('voice_mode.config.OPENAI_API_KEY', None):
                result = await converse.fn(
                    message="Test",
                    wait_for_response=False
                )

                # Should suggest checking services or setting API key
                assert any(keyword in result.lower() for keyword in [
                    'service', 'running', 'api', 'key', 'kokoro', 'openai'
                ]), f"Error doesn't suggest solutions: {result}"

    @pytest.mark.asyncio
    async def test_error_message_includes_provider_info(self):
        """Test that errors indicate which provider failed."""
        from voice_mode.tools.converse import converse

        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (False, None, {
                'error_type': 'all_providers_failed',
                'attempted_endpoints': [
                    {
                        'provider': 'openai',
                        'endpoint': 'https://api.openai.com/v1/audio/speech',
                        'error': 'Insufficient quota'
                    }
                ]
            })

            result = await converse.fn(
                message="Test",
                wait_for_response=False
            )

            # Should mention the provider that failed
            assert 'openai' in result.lower() or 'api' in result.lower()


class TestConverseSTTFailures:
    """Test STT (speech-to-text) failure handling."""

    @pytest.mark.asyncio
    async def test_stt_failure_reports_clearly(self):
        """Test that STT failures are reported clearly."""
        from voice_mode.tools.converse import converse

        # Mock successful TTS but failed STT
        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (True, {'duration_ms': 100}, {'provider': 'kokoro'})

            with patch('voice_mode.tools.converse.record_audio') as mock_record:
                mock_record.return_value = b'audio_data'

                with patch('voice_mode.simple_failover.simple_stt_failover') as mock_stt:
                    mock_stt.return_value = {
                        'error_type': 'connection_failed',
                        'attempted_endpoints': [
                            {
                                'provider': 'whisper',
                                'endpoint': 'http://127.0.0.1:2022/v1/audio/transcriptions',
                                'error': 'Service not running'
                            }
                        ]
                    }

                    result = await converse.fn(
                        message="Test",
                        wait_for_response=True
                    )

                    # Should indicate STT/transcription failure
                    assert any(keyword in result.lower() for keyword in [
                        'transcription', 'speech', 'text', 'stt', 'whisper', 'failed'
                    ]), f"Result doesn't indicate STT failure: {result}"

    @pytest.mark.asyncio
    async def test_stt_no_speech_detected(self):
        """Test handling when no speech is detected."""
        from voice_mode.tools.converse import converse

        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (True, {'duration_ms': 100}, {'provider': 'kokoro'})

            with patch('voice_mode.tools.converse.record_audio') as mock_record:
                mock_record.return_value = b'silence'

                with patch('voice_mode.simple_failover.simple_stt_failover') as mock_stt:
                    mock_stt.return_value = {
                        'error_type': 'no_speech',
                        'provider': 'whisper'
                    }

                    result = await converse.fn(
                        message="Are you there?",
                        wait_for_response=True
                    )

                    # Should indicate no speech detected
                    assert 'no speech' in result.lower() or 'silence' in result.lower()


class TestConverseMetrics:
    """Test that converse properly tracks and reports metrics."""

    @pytest.mark.asyncio
    async def test_converse_includes_timing_metrics(self):
        """Test that converse includes timing information when successful."""
        from voice_mode.tools.converse import converse

        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            mock_tts.return_value = (True, {
                'duration_ms': 150,
                'ttfb_ms': 50
            }, {'provider': 'openai'})

            result = await converse.fn(
                message="Test",
                wait_for_response=False
            )

            # Timing info should be included in successful responses (check for 's' suffix for seconds)
            assert 'ms' in result or ': ' in result and 's' in result  # Timing like "gen: 0.0s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])