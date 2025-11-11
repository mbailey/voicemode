"""
Tests for wait and repeat command functionality.

This test suite covers:
1. play_system_audio() function with audio files and TTS fallback
2. Wait command detection and handling
3. Repeat command detection and handling
"""
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call
import numpy as np

from voice_mode.core import play_system_audio
from voice_mode.tools.converse import should_wait, should_repeat, WAIT_PHRASES, REPEAT_PHRASES


class TestPlaySystemAudio:
    """Tests for the play_system_audio function."""

    @pytest.mark.asyncio
    async def test_play_system_audio_with_existing_file(self):
        """Test that system audio plays successfully when audio file exists."""
        with patch('voice_mode.core.Path') as mock_path, \
             patch('voice_mode.core.AudioSegment') as mock_audio_segment, \
             patch('voice_mode.core.NonBlockingAudioPlayer') as mock_player:

            # Mock file existence
            mock_file = MagicMock()
            mock_file.exists.return_value = True
            mock_path.return_value.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_file

            # Mock audio loading
            mock_audio = MagicMock()
            mock_audio.channels = 1
            mock_audio.frame_rate = 24000
            mock_audio.get_array_of_samples.return_value = np.array([0, 1000, -1000], dtype=np.int16)
            mock_audio_segment.from_file.return_value = mock_audio

            # Mock player
            mock_player_instance = MagicMock()
            mock_player.return_value = mock_player_instance

            # Test
            result = await play_system_audio("waiting-1-minute", fallback_text="Waiting")

            assert result is True
            mock_player_instance.play.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_system_audio_fallback_to_tts(self):
        """Test that system audio falls back to TTS when audio file doesn't exist."""
        with patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:

            # Mock TTS success
            mock_tts.return_value = (True, {"ttfa": 0.5}, {"voice": "af_sky"})

            # Test with non-existent audio file to trigger fallback
            result = await play_system_audio("test-nonexistent-audio-file", fallback_text="Waiting one minute")

            assert result is True
            # Verify TTS was called with correct parameters
            mock_tts.assert_called_once()
            call_args = mock_tts.call_args
            assert call_args.kwargs['text'] == "Waiting one minute"
            assert call_args.kwargs['voice'] == "af_sky"
            assert call_args.kwargs['model'] == "tts-1"  # Critical: model parameter must be present

    @pytest.mark.asyncio
    async def test_play_system_audio_no_fallback_text(self):
        """Test that system audio returns False when no audio file and no fallback text."""
        with patch('voice_mode.core.Path') as mock_path:

            # Mock file doesn't exist - need to mock all extensions
            def mock_exists(self):
                return False

            mock_candidate = MagicMock()
            mock_candidate.exists = mock_exists

            # Mock the path division to return our mock candidate
            mock_path_instance = MagicMock()
            mock_path_instance.__truediv__ = MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=MagicMock(__truediv__=MagicMock(return_value=mock_candidate)))))))
            mock_path.return_value = mock_path_instance

            # Test without fallback text
            result = await play_system_audio("nonexistent-message")

            assert result is False

    @pytest.mark.asyncio
    async def test_play_system_audio_file_playback_error_fallback(self):
        """Test that TTS fallback works when audio file playback fails."""
        with patch('voice_mode.core.NonBlockingAudioPlayer') as mock_player, \
             patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:

            # Mock player to raise exception during playback
            mock_player_instance = MagicMock()
            mock_player_instance.play.side_effect = Exception("Playback failed")
            mock_player.return_value = mock_player_instance

            # Mock TTS success
            mock_tts.return_value = (True, {"ttfa": 0.5}, {"voice": "af_sky"})

            # Test with existing file that will fail to play
            result = await play_system_audio("waiting-1-minute", fallback_text="Waiting")

            assert result is True
            mock_tts.assert_called_once()


class TestWaitCommandDetection:
    """Tests for wait command detection."""

    def test_should_wait_with_exact_match(self):
        """Test detection of exact wait phrase."""
        assert should_wait("wait") is True
        assert should_wait("Wait") is True
        assert should_wait("WAIT") is True

    def test_should_wait_at_end_of_sentence(self):
        """Test detection when wait phrase is at end of sentence."""
        assert should_wait("Hello please wait") is True
        assert should_wait("I'll come back, wait") is True
        assert should_wait("Just a moment, please wait.") is True

    def test_should_wait_with_punctuation(self):
        """Test detection with trailing punctuation."""
        assert should_wait("wait.") is True
        assert should_wait("wait!") is True
        assert should_wait("wait?") is True

    def test_should_not_wait_in_middle_of_sentence(self):
        """Test that wait phrase in middle of sentence is not detected."""
        assert should_wait("I'll wait here for you") is False
        assert should_wait("wait for me please") is False

    def test_should_wait_with_all_defined_phrases(self):
        """Test all defined wait phrases."""
        for phrase in WAIT_PHRASES:
            assert should_wait(phrase) is True
            assert should_wait(f"Hello, {phrase}") is True


class TestRepeatCommandDetection:
    """Tests for repeat command detection."""

    def test_should_repeat_with_exact_match(self):
        """Test detection of exact repeat phrase."""
        assert should_repeat("repeat") is True
        assert should_repeat("Repeat") is True
        assert should_repeat("REPEAT") is True

    def test_should_repeat_at_end_of_sentence(self):
        """Test detection when repeat phrase is at end of sentence."""
        assert should_repeat("Can you repeat") is True
        assert should_repeat("I didn't hear, please repeat.") is True
        # Test other valid repeat phrases
        assert should_repeat("Sorry, what") is True
        assert should_repeat("I'm sorry, pardon") is True

    def test_should_repeat_with_punctuation(self):
        """Test detection with trailing punctuation."""
        assert should_repeat("repeat.") is True
        assert should_repeat("repeat!") is True
        assert should_repeat("repeat?") is True

    def test_should_not_repeat_in_middle_of_sentence(self):
        """Test that repeat phrase in middle of sentence is not detected."""
        assert should_repeat("I repeat that this is important") is False
        assert should_repeat("repeat after me") is False

    def test_should_repeat_with_all_defined_phrases(self):
        """Test all defined repeat phrases."""
        for phrase in REPEAT_PHRASES:
            assert should_repeat(phrase) is True
            assert should_repeat(f"Hello, {phrase}") is True


class TestWaitCommandIntegration:
    """Integration tests for wait command flow."""

    @pytest.mark.asyncio
    async def test_wait_command_plays_waiting_audio(self):
        """Test that wait command triggers waiting-1-minute audio."""
        # Test wait command detection
        response_text = "Hello please wait"
        assert should_wait(response_text) is True

        # Test with actual play_system_audio using mocks
        with patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 0.5}, {"voice": "af_sky"})

            # Call play_system_audio with non-existent file to trigger fallback
            result = await play_system_audio("test-waiting", fallback_text="Waiting one minute")

            # Verify it succeeded and used TTS
            assert result is True
            mock_tts.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_command_plays_ready_audio_after_delay(self):
        """Test that ready-to-listen audio plays after wait period."""
        with patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 0.5}, {"voice": "af_sky"})

            # Simulate the full wait flow from converse.py
            response_text = "please wait"
            WAIT_DURATION = 0.01  # Use very short duration for testing

            if should_wait(response_text):
                await play_system_audio("test-waiting-1", fallback_text="Waiting one minute")
                await asyncio.sleep(WAIT_DURATION)
                await play_system_audio("test-ready", fallback_text="Ready to listen")

            # Verify both audios were played via TTS
            assert mock_tts.call_count == 2


class TestRepeatCommandIntegration:
    """Integration tests for repeat command flow."""

    @pytest.mark.asyncio
    async def test_repeat_command_plays_repeating_audio(self):
        """Test that repeat command triggers repeating audio."""
        # Test repeat command detection
        response_text = "please repeat"
        assert should_repeat(response_text) is True

        # Test with actual play_system_audio using mocks
        with patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 0.5}, {"voice": "af_sky"})

            # Call play_system_audio with non-existent file to trigger fallback
            result = await play_system_audio("test-repeating", fallback_text="Repeating")

            # Verify it succeeded and used TTS
            assert result is True
            mock_tts.assert_called_once()

    @pytest.mark.asyncio
    async def test_repeat_command_multiple_times(self):
        """Test that repeat command can be triggered multiple times."""
        with patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = (True, {"ttfa": 0.5}, {"voice": "af_sky"})

            # Simulate multiple repeat requests
            for _ in range(3):
                response_text = "repeat"
                if should_repeat(response_text):
                    await play_system_audio("test-repeat", fallback_text="Repeating")

            # Verify audio was played 3 times via TTS
            assert mock_tts.call_count == 3


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_wait_and_repeat_phrases_dont_overlap(self):
        """Ensure wait and repeat phrases don't trigger each other."""
        for wait_phrase in WAIT_PHRASES:
            assert should_repeat(wait_phrase) is False, f"Wait phrase '{wait_phrase}' incorrectly triggers repeat"

        for repeat_phrase in REPEAT_PHRASES:
            assert should_wait(repeat_phrase) is False, f"Repeat phrase '{repeat_phrase}' incorrectly triggers wait"

    def test_empty_string_detection(self):
        """Test that empty strings don't trigger commands."""
        assert should_wait("") is False
        assert should_repeat("") is False

    def test_whitespace_only_detection(self):
        """Test that whitespace-only strings don't trigger commands."""
        assert should_wait("   ") is False
        assert should_repeat("   ") is False

    @pytest.mark.asyncio
    async def test_tts_fallback_failure_handling(self):
        """Test handling when both audio file and TTS fallback fail."""
        with patch('voice_mode.simple_failover.simple_tts_failover', new_callable=AsyncMock) as mock_tts:

            # Mock TTS failure
            mock_tts.return_value = (False, None, None)

            # Test - should still return False gracefully (using non-existent audio file)
            result = await play_system_audio("nonexistent-test-audio", fallback_text="Waiting")

            assert result is False
            mock_tts.assert_called_once()
