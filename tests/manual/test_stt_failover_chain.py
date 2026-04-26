"""Manual smoke test: full STT failover chain with VOICEMODE_STT_MODEL set.

Implements the manual smoke described in VM-1100 test-004. Instead of
requiring an interactive `voicemode converse` session, this script drives
``simple_stt_failover()`` directly against running services and asserts which
endpoint succeeds for each scenario in the failover chain.

Scenarios:
    A. All three URLs alive            -> mlx-audio (8890) handles the request.
    B. mlx-audio "down" (bad URL)      -> whisper.cpp (2022) handles it.
    C. Both local "down" (bad URLs)    -> OpenAI handles it; we verify the
       outbound model kwarg is 'whisper-1' via a patched AsyncOpenAI client
       (avoiding real credit consumption).

Prerequisites:
    - mlx-audio listening on http://127.0.0.1:8890/v1
    - whisper.cpp listening on http://127.0.0.1:2022/v1
    - A WAV sample at WAV_PATH (defaults to a recent one in ~/.voicemode/audio/).

Run:
    cd worktree && uv run python -m tests.manual.test_stt_failover_chain
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

WAV_PATH = Path.home() / ".voicemode" / "audio" / "no_speech_20260427_013641.wav"

OPENAI_URL = "https://api.openai.com/v1"
MLX_AUDIO_URL = "http://127.0.0.1:8890/v1"
WHISPER_CPP_URL = "http://127.0.0.1:2022/v1"
DEAD_URL_FOR_MLX = "http://127.0.0.1:18890/v1"
DEAD_URL_FOR_WHISPER_CPP = "http://127.0.0.1:12022/v1"

STT_MODEL = "mlx-community/whisper-large-v3-turbo"


def _set_env_for_chain(stt_base_urls: str) -> None:
    os.environ["VOICEMODE_STT_MODEL"] = STT_MODEL
    os.environ["VOICEMODE_STT_BASE_URLS"] = stt_base_urls


def _reload_config_into(*modules):
    """Re-read STT_MODEL / STT_BASE_URLS / STT_MODELS in voice_mode.config and
    re-bind the names imported into each downstream module."""
    import voice_mode.config as cfg
    cfg.reload_configuration()
    for mod in modules:
        mod.STT_BASE_URLS = cfg.STT_BASE_URLS
        if hasattr(mod, "STT_MODEL"):
            mod.STT_MODEL = cfg.STT_MODEL
        if hasattr(mod, "STT_MODELS"):
            mod.STT_MODELS = cfg.STT_MODELS


async def scenario_a_full_chain():
    print("\n=== Scenario A: full chain alive (expect mlx-audio handles) ===")
    _set_env_for_chain(f"{MLX_AUDIO_URL},{WHISPER_CPP_URL},{OPENAI_URL}")

    from voice_mode import simple_failover, providers
    _reload_config_into(simple_failover, providers)

    with open(WAV_PATH, "rb") as audio_file:
        result = await simple_failover.simple_stt_failover(audio_file=audio_file)

    print(f"  Result: {result}")
    assert result is not None and "text" in result, f"expected success, got {result}"
    assert result["endpoint"] == MLX_AUDIO_URL, (
        f"expected mlx-audio to handle, got endpoint={result['endpoint']}"
    )
    print(f"  OK: mlx-audio handled the request, transcribed {result['text']!r}")


async def scenario_b_mlx_down():
    print("\n=== Scenario B: mlx-audio down (expect whisper.cpp handles) ===")
    _set_env_for_chain(f"{DEAD_URL_FOR_MLX},{WHISPER_CPP_URL},{OPENAI_URL}")

    from voice_mode import simple_failover, providers
    _reload_config_into(simple_failover, providers)

    with open(WAV_PATH, "rb") as audio_file:
        result = await simple_failover.simple_stt_failover(audio_file=audio_file)

    print(f"  Result: {result}")
    assert result is not None and "text" in result, f"expected success, got {result}"
    assert result["endpoint"] == WHISPER_CPP_URL, (
        f"expected whisper.cpp to handle, got endpoint={result['endpoint']}"
    )
    print(f"  OK: whisper.cpp handled the request, transcribed {result['text']!r}")


async def scenario_c_both_local_down():
    print("\n=== Scenario C: both local down (expect OpenAI handles, model='whisper-1') ===")
    _set_env_for_chain(f"{DEAD_URL_FOR_MLX},{DEAD_URL_FOR_WHISPER_CPP},{OPENAI_URL}")

    from voice_mode import simple_failover, providers
    _reload_config_into(simple_failover, providers)

    captured = {}
    real_aoai = simple_failover.AsyncOpenAI

    def fake_aoai_factory(*args, base_url=None, **kwargs):
        """Only stub the OpenAI endpoint; for dead local URLs, return a real
        AsyncOpenAI client so the connection genuinely fails and triggers
        failover."""
        if base_url == OPENAI_URL:
            instance = AsyncMock()

            async def fake_create(**create_kwargs):
                captured.update(create_kwargs)
                captured["__base_url__"] = base_url
                return "ok-from-openai-mock"

            instance.audio.transcriptions.create = AsyncMock(side_effect=fake_create)
            return instance
        return real_aoai(*args, base_url=base_url, **kwargs)

    with patch("voice_mode.simple_failover.AsyncOpenAI", side_effect=fake_aoai_factory):
        with open(WAV_PATH, "rb") as audio_file:
            result = await simple_failover.simple_stt_failover(audio_file=audio_file)

    print(f"  Result: {result}")
    print(f"  Captured kwargs: model={captured.get('model')!r}")
    assert result is not None and result.get("text") == "ok-from-openai-mock", (
        f"expected the mocked OpenAI call to succeed, got {result}"
    )
    assert result["endpoint"] == OPENAI_URL, (
        f"expected openai endpoint, got {result['endpoint']}"
    )
    assert captured.get("model") == "whisper-1", (
        f"expected outbound model='whisper-1' (OpenAI override), got {captured.get('model')!r}"
    )
    print("  OK: OpenAI received the call with model='whisper-1' (override applied).")


async def main():
    if not WAV_PATH.exists():
        print(f"ERROR: missing WAV sample at {WAV_PATH}", file=sys.stderr)
        sys.exit(2)

    print(f"Audio sample: {WAV_PATH} ({WAV_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"VOICEMODE_STT_MODEL = {STT_MODEL}")

    await scenario_a_full_chain()
    await scenario_b_mlx_down()
    await scenario_c_both_local_down()

    print("\nAll three failover-chain scenarios passed.")


if __name__ == "__main__":
    asyncio.run(main())
