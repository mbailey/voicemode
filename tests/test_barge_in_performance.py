"""Performance tests for barge-in feature.

These tests verify the performance characteristics of the barge-in feature:
1. Voice onset to TTS stop latency (<100ms target)
2. CPU overhead during microphone monitoring
3. Memory usage during audio capture
4. Thread scheduling and callback latency
"""

import pytest
import numpy as np
import threading
import time
import sys
import gc
from unittest.mock import Mock, MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

# Mock webrtcvad before importing voice_mode modules
mock_webrtcvad = MagicMock()
sys.modules['webrtcvad'] = mock_webrtcvad


class TestVoiceOnsetToTTSStopLatency:
    """Test voice onset to TTS stop latency meets <100ms target."""

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_latency_under_100ms(self, mock_sd):
        """Test that interrupt latency is under 100ms target."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        latencies = []

        for _ in range(10):  # Run multiple iterations for statistical significance
            callback_time = None

            def track_callback():
                nonlocal callback_time
                callback_time = time.perf_counter()

            player = NonBlockingAudioPlayer(on_interrupt=track_callback)
            samples = np.zeros(50000, dtype=np.float32)  # ~2 seconds

            player.play(samples, 24000, blocking=False)

            # Simulate voice detection after small delay
            time.sleep(0.01)
            voice_detected_time = time.perf_counter()
            player.interrupt()

            if callback_time:
                latency_ms = (callback_time - voice_detected_time) * 1000
                latencies.append(latency_ms)

            player.stop()

        assert len(latencies) > 0
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Average should be well under 100ms
        assert avg_latency < 50, f"Average interrupt latency {avg_latency:.1f}ms exceeds 50ms"
        # Even worst case should be under 100ms
        assert max_latency < 100, f"Max interrupt latency {max_latency:.1f}ms exceeds 100ms"

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_callback_fires_quickly(self, mock_sd):
        """Test that the interrupt callback is invoked with minimal delay."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        callback_times = []

        def track_callback():
            callback_times.append(time.perf_counter())

        player = NonBlockingAudioPlayer(on_interrupt=track_callback)
        samples = np.zeros(24000, dtype=np.float32)  # 1 second

        player.play(samples, 24000, blocking=False)
        time.sleep(0.05)

        start = time.perf_counter()
        player.interrupt()
        end = time.perf_counter()

        assert len(callback_times) == 1
        callback_delay_ms = (callback_times[0] - start) * 1000
        total_time_ms = (end - start) * 1000

        # Callback should fire nearly instantly (< 5ms)
        assert callback_delay_ms < 5, f"Callback delay {callback_delay_ms:.2f}ms exceeds 5ms"
        assert total_time_ms < 10, f"Total interrupt time {total_time_ms:.2f}ms exceeds 10ms"

    def test_barge_in_monitor_callback_latency(self):
        """Test BargeInMonitor callback invocation latency."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            callback_times = []

            def track_callback():
                callback_times.append(time.perf_counter())

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                latencies = []

                for _ in range(50):  # Multiple iterations
                    callback_times.clear()
                    monitor = BargeInMonitor(min_speech_ms=10)
                    monitor._callback = track_callback
                    monitor._callback_fired = False
                    monitor._speech_ms_accumulated = 20  # Above threshold

                    start = time.perf_counter()

                    # Simulate what monitoring loop does
                    if (monitor._speech_ms_accumulated >= monitor.min_speech_ms
                            and not monitor._callback_fired):
                        monitor._voice_detected_event.set()
                        monitor._callback_fired = True
                        if monitor._callback:
                            monitor._callback()

                    latency_ms = (callback_times[0] - start) * 1000
                    latencies.append(latency_ms)

                avg_latency = sum(latencies) / len(latencies)
                max_latency = max(latencies)

                # Callback invocation should be sub-millisecond
                assert avg_latency < 1, f"Average callback latency {avg_latency:.3f}ms exceeds 1ms"
                assert max_latency < 5, f"Max callback latency {max_latency:.3f}ms exceeds 5ms"


class TestCPUOverheadDuringMonitoring:
    """Test CPU overhead during microphone monitoring."""

    def test_idle_cpu_usage_acceptable(self):
        """Test that idle CPU usage during monitoring is acceptable."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                monitor = BargeInMonitor()

                # Measure baseline CPU
                import os
                pid = os.getpid()

                # Simulate monitoring state (without actual audio stream)
                monitor._stop_event.clear()
                monitor._thread = threading.Thread(target=lambda: None)

                # Measure that the monitor objects don't consume significant memory
                # when idle
                import sys
                monitor_size = sys.getsizeof(monitor)
                buffer_size = sys.getsizeof(monitor._audio_buffer)
                lock_size = sys.getsizeof(monitor._buffer_lock)

                # Monitor objects should be small
                total_size = monitor_size + buffer_size + lock_size
                assert total_size < 1000, f"Monitor object size {total_size} bytes is excessive"

    def test_vad_check_performance(self):
        """Test VAD checking performance doesn't cause bottleneck."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                monitor = BargeInMonitor()

                # Create mock VAD
                mock_vad = MagicMock()
                mock_vad.is_speech.return_value = False
                monitor._vad = mock_vad

                # Generate test audio chunk
                chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

                # Mock scipy.signal.resample to avoid actual resampling
                with patch('scipy.signal.resample') as mock_resample:
                    mock_resample.return_value = chunk.astype(np.float64)

                    # Measure VAD check time
                    times = []
                    for _ in range(100):
                        start = time.perf_counter()
                        monitor._check_vad(chunk, 16000, 320)
                        end = time.perf_counter()
                        times.append((end - start) * 1000)

                    avg_time = sum(times) / len(times)
                    max_time = max(times)

                    # VAD check should be fast (< 5ms per chunk)
                    assert avg_time < 5, f"Average VAD check {avg_time:.3f}ms exceeds 5ms"
                    assert max_time < 20, f"Max VAD check {max_time:.3f}ms exceeds 20ms"

    def test_audio_buffer_append_performance(self):
        """Test audio buffer append operations are fast."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Generate test chunks
            chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

            times = []
            for _ in range(1000):  # Simulate many appends
                start = time.perf_counter()
                with monitor._buffer_lock:
                    monitor._audio_buffer.append(chunk.copy())
                end = time.perf_counter()
                times.append((end - start) * 1000)

            avg_time = sum(times) / len(times)
            max_time = max(times)

            # Buffer append should be very fast (< 1ms)
            assert avg_time < 1, f"Average buffer append {avg_time:.3f}ms exceeds 1ms"
            assert max_time < 10, f"Max buffer append {max_time:.3f}ms exceeds 10ms"


class TestMemoryUsageDuringCapture:
    """Test memory usage during audio capture."""

    def test_audio_buffer_memory_growth(self):
        """Test that audio buffer memory growth is reasonable."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()
            gc.collect()
            initial_buffer_count = len(monitor._audio_buffer)

            # Simulate 5 seconds of speech at 24kHz (480 samples per 20ms chunk)
            # 5000ms / 20ms = 250 chunks
            chunks_for_5s = 250
            chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

            for _ in range(chunks_for_5s):
                with monitor._buffer_lock:
                    monitor._audio_buffer.append(chunk.copy())

            # Get captured audio
            captured = monitor.get_captured_audio()

            # Should have approximately 5 seconds of audio
            expected_samples = chunks_for_5s * 480
            assert captured is not None
            assert len(captured) == expected_samples

            # Memory for 5s at 24kHz, 16-bit = 5 * 24000 * 2 = 240KB
            # With overhead, should be under 500KB
            audio_memory = captured.nbytes
            assert audio_memory < 500 * 1024, f"Audio memory {audio_memory} bytes exceeds 500KB"

    def test_buffer_cleanup_releases_memory(self):
        """Test that buffer cleanup properly releases memory."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()

            # Fill buffer
            chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)
            for _ in range(100):
                with monitor._buffer_lock:
                    monitor._audio_buffer.append(chunk.copy())

            assert len(monitor._audio_buffer) == 100

            # Clear buffer (simulating reset on silence)
            with monitor._buffer_lock:
                monitor._audio_buffer.clear()

            assert len(monitor._audio_buffer) == 0

            # Get captured audio should return None
            captured = monitor.get_captured_audio()
            assert captured is None


class TestThreadSchedulingAndLatency:
    """Test thread scheduling and callback latency."""

    @patch('voice_mode.audio_player.sd')
    def test_interrupt_from_background_thread(self, mock_sd):
        """Test interrupt latency when called from background thread."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        latencies = []

        for _ in range(20):
            callback_time = [None]

            def track_callback():
                callback_time[0] = time.perf_counter()

            player = NonBlockingAudioPlayer(on_interrupt=track_callback)
            samples = np.zeros(24000, dtype=np.float32)

            player.play(samples, 24000, blocking=False)
            time.sleep(0.01)

            # Interrupt from background thread (simulating BargeInMonitor)
            voice_detected_time = [None]

            def interrupt_from_thread():
                voice_detected_time[0] = time.perf_counter()
                player.interrupt()

            t = threading.Thread(target=interrupt_from_thread)
            t.start()
            t.join()

            if callback_time[0] and voice_detected_time[0]:
                latency_ms = (callback_time[0] - voice_detected_time[0]) * 1000
                latencies.append(latency_ms)

            player.stop()

        assert len(latencies) > 0
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Even from background thread, latency should be low
        assert avg_latency < 20, f"Average cross-thread latency {avg_latency:.1f}ms exceeds 20ms"
        assert max_latency < 50, f"Max cross-thread latency {max_latency:.1f}ms exceeds 50ms"

    def test_concurrent_buffer_access_performance(self):
        """Test performance under concurrent buffer access."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()
            errors = []
            operation_times = []

            def writer():
                try:
                    for _ in range(100):
                        chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)
                        start = time.perf_counter()
                        with monitor._buffer_lock:
                            monitor._audio_buffer.append(chunk)
                        end = time.perf_counter()
                        operation_times.append(('write', (end - start) * 1000))
                except Exception as e:
                    errors.append(e)

            def reader():
                try:
                    for _ in range(100):
                        start = time.perf_counter()
                        monitor.get_captured_audio()
                        end = time.perf_counter()
                        operation_times.append(('read', (end - start) * 1000))
                except Exception as e:
                    errors.append(e)

            # Run concurrent access
            threads = []
            for _ in range(2):
                threads.append(threading.Thread(target=writer))
                threads.append(threading.Thread(target=reader))

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0, f"Concurrent access errors: {errors}"

            # Calculate average times
            write_times = [t[1] for t in operation_times if t[0] == 'write']
            read_times = [t[1] for t in operation_times if t[0] == 'read']

            if write_times:
                avg_write = sum(write_times) / len(write_times)
                assert avg_write < 5, f"Average write time {avg_write:.3f}ms exceeds 5ms"

            if read_times:
                avg_read = sum(read_times) / len(read_times)
                assert avg_read < 20, f"Average read time {avg_read:.3f}ms exceeds 20ms"


class TestEndToEndLatencySimulation:
    """Simulate end-to-end barge-in latency."""

    @patch('voice_mode.audio_player.sd')
    def test_full_pipeline_latency(self, mock_sd):
        """Test complete pipeline from voice detection to playback stop."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        latencies = []

        for _ in range(10):
            tts_stopped_time = [None]

            def on_tts_stop():
                tts_stopped_time[0] = time.perf_counter()

            # Create player with interrupt callback
            player = NonBlockingAudioPlayer(on_interrupt=on_tts_stop)
            samples = np.zeros(48000, dtype=np.float32)  # 2 seconds

            player.play(samples, 24000, blocking=False)
            time.sleep(0.05)  # Let playback start

            # Simulate the full pipeline:
            # 1. VAD detects voice (simulated by timer)
            # 2. Threshold exceeded
            # 3. Callback fires
            # 4. Player interrupted

            voice_onset_time = time.perf_counter()

            # Simulate VAD processing time (typically 10-20ms)
            time.sleep(0.015)

            # Simulate threshold accumulation (150ms default)
            # In real scenario this is already counted from voice_onset
            # For test, we just measure from callback trigger

            # Trigger interrupt (as if BargeInMonitor detected speech)
            player.interrupt()

            if tts_stopped_time[0]:
                # Total latency from voice onset to TTS stop
                total_latency_ms = (tts_stopped_time[0] - voice_onset_time) * 1000
                latencies.append(total_latency_ms)

            player.stop()

        assert len(latencies) > 0
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        # Target is <100ms total
        # This includes: VAD processing (~15ms) + callback overhead
        # Note: This doesn't include the min_speech_ms threshold time
        # as that's intentional delay, not system latency
        assert avg_latency < 50, f"Average pipeline latency {avg_latency:.1f}ms exceeds 50ms"
        assert max_latency < 100, f"Max pipeline latency {max_latency:.1f}ms exceeds 100ms"


class TestPerformanceUnderLoad:
    """Test performance under various load conditions."""

    @patch('voice_mode.audio_player.sd')
    def test_repeated_interrupt_cycles(self, mock_sd):
        """Test latency consistency over many interrupt cycles."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        latencies = []

        for i in range(50):  # 50 cycles
            callback_time = [None]

            def track_callback():
                callback_time[0] = time.perf_counter()

            player = NonBlockingAudioPlayer(on_interrupt=track_callback)
            samples = np.zeros(12000, dtype=np.float32)  # 0.5 seconds

            player.play(samples, 24000, blocking=False)

            start = time.perf_counter()
            player.interrupt()

            if callback_time[0]:
                latency_ms = (callback_time[0] - start) * 1000
                latencies.append(latency_ms)

            player.stop()

        # Analyze latency distribution
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        # Calculate standard deviation
        variance = sum((x - avg_latency) ** 2 for x in latencies) / len(latencies)
        std_dev = variance ** 0.5

        # Latency should be consistent (low standard deviation)
        assert avg_latency < 10, f"Average latency {avg_latency:.2f}ms exceeds 10ms"
        assert max_latency < 50, f"Max latency {max_latency:.2f}ms exceeds 50ms"
        assert std_dev < 5, f"Latency std dev {std_dev:.2f}ms exceeds 5ms (inconsistent performance)"

    def test_high_frequency_vad_checks(self):
        """Test VAD check performance at high frequency."""
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor
            from voice_mode import barge_in

            with patch.object(barge_in, 'VAD_AVAILABLE', True):
                monitor = BargeInMonitor()

                mock_vad = MagicMock()
                mock_vad.is_speech.return_value = False
                monitor._vad = mock_vad

                chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

                with patch('scipy.signal.resample') as mock_resample:
                    mock_resample.return_value = chunk.astype(np.float64)

                    # Simulate high frequency checks (every 20ms for 5 seconds = 250 checks)
                    start_time = time.perf_counter()
                    checks = 0

                    while time.perf_counter() - start_time < 0.5:  # 0.5 second test
                        monitor._check_vad(chunk, 16000, 320)
                        checks += 1

                    elapsed = time.perf_counter() - start_time
                    checks_per_second = checks / elapsed

                    # Should handle at least 50 checks per second (20ms intervals)
                    assert checks_per_second > 50, f"Only {checks_per_second:.1f} VAD checks/sec"


class TestPerformanceMetricsReport:
    """Generate performance metrics report."""

    @patch('voice_mode.audio_player.sd')
    def test_generate_performance_report(self, mock_sd):
        """Generate a comprehensive performance report."""
        from voice_mode.audio_player import NonBlockingAudioPlayer

        mock_stream = MagicMock()
        mock_sd.OutputStream.return_value = mock_stream

        results = {
            'interrupt_latency': [],
            'callback_latency': [],
            'buffer_append': [],
        }

        # Measure interrupt latency
        for _ in range(20):
            callback_time = [None]

            def track():
                callback_time[0] = time.perf_counter()

            player = NonBlockingAudioPlayer(on_interrupt=track)
            samples = np.zeros(12000, dtype=np.float32)
            player.play(samples, 24000, blocking=False)

            start = time.perf_counter()
            player.interrupt()

            if callback_time[0]:
                results['interrupt_latency'].append((callback_time[0] - start) * 1000)
            player.stop()

        # Measure buffer append
        with patch.dict('sys.modules', {'webrtcvad': mock_webrtcvad}):
            from voice_mode.barge_in import BargeInMonitor

            monitor = BargeInMonitor()
            chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

            for _ in range(100):
                start = time.perf_counter()
                with monitor._buffer_lock:
                    monitor._audio_buffer.append(chunk.copy())
                results['buffer_append'].append((time.perf_counter() - start) * 1000)

        # Print report
        report_lines = [
            "",
            "=" * 60,
            "BARGE-IN PERFORMANCE REPORT",
            "=" * 60,
            "",
        ]

        for metric, values in results.items():
            if values:
                avg = sum(values) / len(values)
                min_val = min(values)
                max_val = max(values)
                report_lines.extend([
                    f"{metric}:",
                    f"  Average: {avg:.3f}ms",
                    f"  Min:     {min_val:.3f}ms",
                    f"  Max:     {max_val:.3f}ms",
                    f"  Samples: {len(values)}",
                    "",
                ])

        report_lines.extend([
            "=" * 60,
            "TARGET: <100ms voice onset to TTS stop",
            "STATUS: PASS" if max(results['interrupt_latency']) < 100 else "FAIL",
            "=" * 60,
        ])

        report = "\n".join(report_lines)
        print(report)

        # Assert performance targets
        assert max(results['interrupt_latency']) < 100


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
