"""Cancelling a turns[] converse must stop the playback thread.

`_speak_turns_pipeline` plays each turn via `_play_samples_blocking` on the
default ThreadPoolExecutor (`asyncio.to_thread`). Cancelling the awaiting
coroutine -- ESC, or the transport-close cancellation VM-2015 restored --
abandons the *future* but not the *thread*: the player keeps running to the
end of the turn. That is the same shape VM-2015 fixed for recording.

On shutdown it is worse than stale audio. `mcp.run()` ends in
`asyncio.Runner.close()`, which joins the default executor (up to 300s), so
the server process cannot exit while the turn is still playing. The client has
already started a replacement process, and both now hold an output stream.

The fix mirrors the recording stop flag: the caller sets a `threading.Event`
when it is cancelled, and the playback thread polls it and stops the player.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_mode.tools import converse
from voice_mode.tools.converse import _normalize_turns, _play_samples_blocking, _speak_turns_pipeline


class _FakePlayer:
    """Stands in for NonBlockingAudioPlayer without an audio device.

    Playback "completes" only when ``finish()`` or ``stop()`` is called. The
    blocking path is bounded at 5s so that, against the unfixed code, a test
    fails in bounded time instead of hanging the suite.
    """

    instances: list = []

    def __init__(self):
        self.playback_complete = threading.Event()
        self.started = threading.Event()
        self.stop = MagicMock(side_effect=self.playback_complete.set)
        self.wait = MagicMock()
        self.stream = None
        _FakePlayer.instances.append(self)

    def play(self, samples, sample_rate, blocking=False):
        self.started.set()
        if blocking:
            self.playback_complete.wait(timeout=5.0)

    def finish(self):
        self.playback_complete.set()


@pytest.fixture(autouse=True)
def _fake_player():
    _FakePlayer.instances = []
    with patch.object(converse, "NonBlockingAudioPlayer", _FakePlayer):
        yield


def _wait_for(event: threading.Event, timeout: float = 2.0) -> bool:
    return event.wait(timeout=timeout)


class TestPlaySamplesBlocking:
    def test_natural_completion_waits_and_does_not_stop(self):
        done = threading.Event()

        def run():
            _play_samples_blocking(np.zeros(16, dtype=np.float32), 24000, stop_event=threading.Event())
            done.set()

        threading.Thread(target=run, daemon=True).start()
        player = None
        for _ in range(100):
            if _FakePlayer.instances:
                player = _FakePlayer.instances[0]
                break
            time.sleep(0.01)
        assert player is not None and _wait_for(player.started)
        player.finish()

        assert _wait_for(done), "playback thread did not return after natural completion"
        player.wait.assert_called_once()
        player.stop.assert_not_called()

    def test_stop_event_stops_the_player_and_returns(self):
        stop = threading.Event()
        done = threading.Event()

        def run():
            _play_samples_blocking(np.zeros(16, dtype=np.float32), 24000, stop_event=stop)
            done.set()

        threading.Thread(target=run, daemon=True).start()
        for _ in range(100):
            if _FakePlayer.instances:
                break
            time.sleep(0.01)
        player = _FakePlayer.instances[0]
        assert _wait_for(player.started)

        started = time.monotonic()
        stop.set()

        assert _wait_for(done), "playback thread kept running after stop_event was set"
        assert time.monotonic() - started < 1.0
        player.stop.assert_called_once()

    def test_stop_event_already_set_plays_nothing(self):
        stop = threading.Event()
        stop.set()

        _play_samples_blocking(np.zeros(16, dtype=np.float32), 24000, stop_event=stop)

        assert all(not p.started.is_set() for p in _FakePlayer.instances)

    def test_without_stop_event_still_plays_to_completion(self):
        """Callers that pass no stop_event keep the old blocking behaviour."""
        done = threading.Event()

        def run():
            _play_samples_blocking(np.zeros(16, dtype=np.float32), 24000)
            done.set()

        threading.Thread(target=run, daemon=True).start()
        for _ in range(100):
            if _FakePlayer.instances:
                break
            time.sleep(0.01)
        player = _FakePlayer.instances[0]
        assert _wait_for(player.started)
        assert not done.wait(timeout=0.2), "returned before playback completed"

        player.finish()
        assert _wait_for(done)
        player.stop.assert_not_called()


class TestPipelineCancellation:
    async def test_cancelling_the_pipeline_stops_the_playback_thread(self):
        """The defect: the worker thread outlived the cancelled coroutine."""
        turns = _normalize_turns(
            [{"say": "a long turn"}, {"say": "never reached"}],
            default_voice="default", default_pause_after_ms=0,
            default_tts_instructions=None, default_speed=None,
        )

        async def fake_synth(**kw):
            return (True, np.zeros(16, dtype=np.float32), 24000, {"generation": 0.0}, {})

        real_play = converse._play_samples_blocking
        worker_returned = threading.Event()

        def tracked_play(*args, **kwargs):
            try:
                return real_play(*args, **kwargs)
            finally:
                worker_returned.set()

        with patch.object(converse, "synthesize_turn_with_failover", side_effect=fake_synth), \
             patch.object(converse, "_play_samples_blocking", tracked_play):
            task = asyncio.create_task(_speak_turns_pipeline(
                turns, tts_model=None, tts_provider=None, audio_format=None,
                resolved_ref_text=None, should_skip_tts=False,
            ))
            for _ in range(200):
                if _FakePlayer.instances and _FakePlayer.instances[0].started.is_set():
                    break
                await asyncio.sleep(0.01)
            player = _FakePlayer.instances[0]
            assert player.started.is_set(), "playback never started"

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            # Poll from the event loop rather than blocking it.
            for _ in range(100):
                if worker_returned.is_set():
                    break
                await asyncio.sleep(0.01)

        assert worker_returned.is_set(), (
            "playback thread still running 1s after cancellation -- it would hold "
            "the executor join in asyncio.Runner.close() and keep the process alive"
        )
        player.stop.assert_called_once()
        # Only the first turn ever started.
        assert len(_FakePlayer.instances) == 1
