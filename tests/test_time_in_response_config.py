"""Tests for the VOICEMODE_TIME_IN_RESPONSE config global (VM-1961, do-002).

Follows the existing VOICEMODE_* boolean env convention (config.py:555-618,
e.g. SKIP_TTS) -- default off, truthy strings ("true"/"1"/"yes"/"on",
case-insensitive) turn it on.
"""

import importlib

import voice_mode.config as cfg


def test_time_in_response_importable_and_off_by_default_when_unset(monkeypatch):
    monkeypatch.delenv("VOICEMODE_TIME_IN_RESPONSE", raising=False)
    importlib.reload(cfg)
    try:
        assert cfg.TIME_IN_RESPONSE is False
    finally:
        importlib.reload(cfg)  # restore real environment for subsequent tests


def test_time_in_response_true_values(monkeypatch):
    for value in ("true", "True", "TRUE", "1", "yes", "on"):
        monkeypatch.setenv("VOICEMODE_TIME_IN_RESPONSE", value)
        importlib.reload(cfg)
        assert cfg.TIME_IN_RESPONSE is True, f"expected True for {value!r}"
    monkeypatch.delenv("VOICEMODE_TIME_IN_RESPONSE", raising=False)
    importlib.reload(cfg)


def test_time_in_response_false_values(monkeypatch):
    for value in ("false", "0", "no", "off", "garbage"):
        monkeypatch.setenv("VOICEMODE_TIME_IN_RESPONSE", value)
        importlib.reload(cfg)
        assert cfg.TIME_IN_RESPONSE is False, f"expected False for {value!r}"
    monkeypatch.delenv("VOICEMODE_TIME_IN_RESPONSE", raising=False)
    importlib.reload(cfg)
