"""Tests for faster-whisper (speaches) provider detection."""
from voice_mode.provider_discovery import detect_provider_type


def test_detect_faster_whisper_by_port():
    assert detect_provider_type("http://127.0.0.1:2023/v1") == "faster-whisper"


def test_detect_whisper_cpp_still_2022():
    assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
