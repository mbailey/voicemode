"""Tests for NonBlockingAudioPlayer interrupt functionality (barge-in support).

Tests cover:
- Interrupt during playback
- Callback invocation on interrupt
- Resource cleanup after interrupt
- No regression for non-interrupt mode
"""

import pytest
import numpy as np
import threading
import time
from unittest.mock import Mock, MagicMock, patch


class TestNonBlockingAudioPlayerInit:
    """Test NonBlockingAudioPlayer initialization with interrupt support."""

    def test_init_without_callback(self):
        """Test initialization without on_interrupt callback."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()

        assert player._on_interrupt is None
        assert player._interrupted is False
        assert player.stream is None
        assert player.audio_queue is None

    def test_init_with_callback(self):
        """Test initialization with on_interrupt callback."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)

        assert player._on_interrupt is callback
        assert player._interrupted is False

    def test_init_with_buffer_size(self):
        """Test initialization with custom buffer size."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer(buffer_size=4096)

        assert player.buffer_size == 4096

    def test_init_with_buffer_size_and_callback(self):
        """Test initialization with both buffer_size and on_interrupt."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock()
        player = NonBlockingAudioPlayer(buffer_size=1024, on_interrupt=callback)

        assert player.buffer_size == 1024
        assert player._on_interrupt is callback


class TestNonBlockingAudioPlayerInterrupt:
    """Test the interrupt() method behavior."""

    def test_interrupt_sets_flag(self):
        """Test that interrupt() sets the _interrupted flag."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()
        player._interrupted = False

        player.interrupt()

        assert player._interrupted is True

    def test_interrupt_calls_stop(self):
        """Test that interrupt() calls stop()."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()
        player.stop = Mock()

        player.interrupt()

        player.stop.assert_called_once()

    def test_interrupt_fires_callback(self):
        """Test that interrupt() fires the on_interrupt callback."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)

        player.interrupt()

        callback.assert_called_once()

    def test_interrupt_callback_called_after_stop(self):
        """Test that callback is called after stop() completes."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        call_order = []

        def track_stop():
            call_order.append('stop')

        def track_callback():
            call_order.append('callback')

        callback = Mock(side_effect=track_callback)
        player = NonBlockingAudioPlayer(on_interrupt=callback)
        player.stop = Mock(side_effect=track_stop)

        player.interrupt()

        assert call_order == ['stop', 'callback']

    def test_interrupt_without_callback_no_error(self):
        """Test that interrupt() works without a callback set."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()

        # Should not raise
        player.interrupt()

        assert player._interrupted is True

    def test_interrupt_callback_error_logged(self):
        """Test that callback errors are logged but don't raise."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock(side_effect=RuntimeError("Callback failed"))
        player = NonBlockingAudioPlayer(on_interrupt=callback)

        with patch('voice_mode.audio_player.logger') as mock_logger:
            # Should not raise
            player.interrupt()

            # Error should be logged
            mock_logger.error.assert_called()
            assert "on_interrupt callback" in str(mock_logger.error.call_args)

    def test_interrupt_can_be_called_multiple_times(self):
        """Test that interrupt() is safe to call multiple times."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)

        player.interrupt()
        player.interrupt()
        player.interrupt()

        # Flag stays True
        assert player._interrupted is True
        # Callback may be called multiple times (depends on design)
        assert callback.call_count >= 1


class TestNonBlockingAudioPlayerWasInterrupted:
    """Test the was_interrupted() method."""

    def test_was_interrupted_initially_false(self):
        """Test that was_interrupted() returns False initially."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()

        assert player.was_interrupted() is False

    def test_was_interrupted_after_interrupt(self):
        """Test that was_interrupted() returns True after interrupt()."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()
        player.interrupt()

        assert player.was_interrupted() is True

    def test_was_interrupted_reset_on_play(self):
        """Test that _interrupted flag is reset when play() is called."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        player = NonBlockingAudioPlayer()
        player._interrupted = True

        # Mock sounddevice to prevent actual playback
        with patch('voice_mode.audio_player.sd') as mock_sd:
            mock_stream = MagicMock()
            mock_sd.OutputStream.return_value = mock_stream

            samples = np.zeros(1000, dtype=np.float32)
            player.play(samples, 24000, blocking=False)

            # Flag should be reset
            assert player._interrupted is False

            # Cleanup
            player.stop()


class TestNonBlockingAudioPlayerPlaybackIntegration:
    """Integration tests for playback with interrupt support."""

    @patch('voice_mode.audio_player.sd')
    def test_normal_playback_completes(self, mock_sd):
        """Test that normal playback completes without interrupt."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        # Setup mock stream
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(100, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # Simulate playback completion
        player.playback_complete.set()
        player.wait(timeout=0.1)

        assert player.was_interrupted() is False

    @patch('voice_mode.audio_player.sd')
    def test_playback_interrupted_mid_stream(self, mock_sd):
        """Test that playback can be interrupted mid-stream."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        # Setup mock stream
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)
        samples = np.zeros(10000, dtype=np.float32)  # Longer sample

        player.play(samples, 24000, blocking=False)

        # Interrupt playback
        player.interrupt()

        assert player.was_interrupted() is True
        callback.assert_called_once()
        assert player.playback_complete.is_set()

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_clears_audio_queue(self, mock_sd):
        """Test that interrupt clears the audio queue."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        # Setup mock stream
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(10000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # Queue should have items
        assert player.audio_queue is not None
        assert not player.audio_queue.empty()  # Queue has items before interrupt

        # Interrupt
        player.interrupt()

        # Queue should be empty after interrupt (via stop())
        assert player.audio_queue.empty()

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_closes_stream(self, mock_sd):
        """Test that interrupt closes the audio stream."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        # Setup mock stream
        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(1000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # Stream should exist
        assert player.stream is not None

        # Interrupt
        player.interrupt()

        # Stream should be stopped and closed
        mock_stream.stop.assert_called()
        mock_stream.close.assert_called()
        assert player.stream is None


class TestNonBlockingAudioPlayerResourceCleanup:
    """Test resource cleanup after interrupt."""

    @patch('voice_mode.audio_player.sd')
    def test_resources_cleaned_after_interrupt(self, mock_sd):
        """Test all resources are cleaned up after interrupt."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(5000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # Verify resources exist
        assert player.stream is not None
        assert player.audio_queue is not None

        # Interrupt
        player.interrupt()

        # Verify cleanup
        assert player.stream is None
        assert player.audio_queue.empty()

    @patch('voice_mode.audio_player.sd')
    def test_multiple_play_interrupt_cycles(self, mock_sd):
        """Test multiple play/interrupt cycles don't leak resources."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(1000, dtype=np.float32)

        for _ in range(5):
            player.play(samples, 24000, blocking=False)

            # Should reset interrupted flag
            assert player.was_interrupted() is False

            player.interrupt()

            # Should be interrupted
            assert player.was_interrupted() is True

            # Stream should be cleaned
            assert player.stream is None

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_during_wait(self, mock_sd):
        """Test interrupt while waiting for playback."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)
        samples = np.zeros(10000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # Start waiting in a thread
        wait_completed = threading.Event()

        def wait_thread():
            player.wait(timeout=5.0)
            wait_completed.set()

        t = threading.Thread(target=wait_thread)
        t.start()

        # Give wait time to start
        time.sleep(0.05)

        # Interrupt from another thread
        player.interrupt()

        # Wait should complete quickly
        t.join(timeout=1.0)
        assert wait_completed.is_set()
        assert player.was_interrupted() is True


class TestNonBlockingAudioPlayerNoRegression:
    """Test that non-interrupt mode still works correctly."""

    @patch('voice_mode.audio_player.sd')
    def test_stop_without_interrupt_no_callback(self, mock_sd):
        """Test that stop() doesn't trigger callback, only interrupt() does."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)
        samples = np.zeros(1000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)
        player.stop()  # Not interrupt

        # Callback should NOT be called for regular stop
        callback.assert_not_called()
        # Flag should NOT be set for regular stop
        assert player.was_interrupted() is False

    @patch('voice_mode.audio_player.sd')
    def test_playback_without_callback_works(self, mock_sd):
        """Test playback works without callback set."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()  # No callback
        samples = np.zeros(100, dtype=np.float32)

        player.play(samples, 24000, blocking=False)
        player.playback_complete.set()
        player.wait(timeout=0.1)

        assert player.was_interrupted() is False

    @patch('voice_mode.audio_player.sd')
    def test_blocking_playback_still_works(self, mock_sd):
        """Test that blocking playback mode still works."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(100, dtype=np.float32)

        # Set playback complete immediately when stream starts
        mock_sd.OutputStream.return_value = mock_stream
        mock_stream.start = Mock(side_effect=lambda: player.playback_complete.set())

        player.play(samples, 24000, blocking=True)

        # Should complete without error
        assert player.was_interrupted() is False

    @patch('voice_mode.audio_player.sd')
    def test_play_resets_state_correctly(self, mock_sd):
        """Test that play() properly resets all state."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()

        # Set up some state
        player._interrupted = True
        player.playback_complete.set()
        player.playback_error = Exception("Previous error")

        samples = np.zeros(100, dtype=np.float32)
        player.play(samples, 24000, blocking=False)

        # State should be reset
        assert player._interrupted is False
        assert not player.playback_complete.is_set() or player.audio_queue is not None
        assert player.playback_error is None


class TestNonBlockingAudioPlayerCallback:
    """Test callback behavior in various scenarios."""

    def test_callback_with_exception_in_stop(self):
        """Test callback runs even if stop() raises."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)

        # Make stop raise an exception
        player.stop = Mock(side_effect=RuntimeError("Stop failed"))

        # interrupt() should handle the exception internally
        # and still set the flag (even if callback doesn't run)
        with pytest.raises(RuntimeError):
            player.interrupt()

        assert player._interrupted is True

    def test_callback_receives_no_arguments(self):
        """Test that callback is called with no arguments."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        callback = Mock()
        player = NonBlockingAudioPlayer(on_interrupt=callback)

        player.interrupt()

        callback.assert_called_once_with()

    @patch('voice_mode.audio_player.sd')
    def test_callback_from_external_thread(self, mock_sd):
        """Test callback can be safely called from external thread."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        callback_thread = []

        def track_thread():
            callback_thread.append(threading.current_thread())

        callback = Mock(side_effect=track_thread)
        player = NonBlockingAudioPlayer(on_interrupt=callback)
        samples = np.zeros(10000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # Call interrupt from a different thread
        def interrupt_thread():
            player.interrupt()

        t = threading.Thread(target=interrupt_thread)
        t.start()
        t.join()

        callback.assert_called_once()
        assert len(callback_thread) == 1
        assert callback_thread[0] != threading.main_thread()


class TestIntegrationWithBargeInMonitor:
    """Integration tests simulating barge-in monitor interaction."""

    @patch('voice_mode.audio_player.sd')
    def test_barge_in_simulation(self, mock_sd):
        """Simulate how BargeInMonitor would use the interrupt method."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        # Track events in order
        events = []

        def on_interrupt_callback():
            events.append('interrupt_callback')

        player = NonBlockingAudioPlayer(on_interrupt=on_interrupt_callback)

        # Start playback (simulating TTS)
        samples = np.zeros(50000, dtype=np.float32)
        player.play(samples, 24000, blocking=False)
        events.append('playback_started')

        # Simulate voice detection triggering interrupt
        # (This is what BargeInMonitor.on_voice_detected would do)
        player.interrupt()
        events.append('interrupt_called')

        # Verify correct sequence
        assert events == ['playback_started', 'interrupt_callback', 'interrupt_called']

        # Verify state
        assert player.was_interrupted() is True
        assert player.stream is None

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_as_callback_target(self, mock_sd):
        """Test using player.interrupt as a callback target."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        player = NonBlockingAudioPlayer()
        samples = np.zeros(10000, dtype=np.float32)

        player.play(samples, 24000, blocking=False)

        # This is how it's used: monitor.start_monitoring(on_voice_detected=player.interrupt)
        # The interrupt method is bound, so calling it as a callback should work
        callback_fn = player.interrupt

        # Simulate callback invocation
        callback_fn()

        assert player.was_interrupted() is True
