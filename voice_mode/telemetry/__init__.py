"""
VoiceMode Telemetry Module

Anonymous, opt-in telemetry system for understanding VoiceMode usage patterns.

This module collects privacy-respecting analytics from VoiceMode usage including:
- Session counts and durations (binned for privacy)
- Exchange counts per session
- TTS/STT provider usage
- Success/failure rates
- Transport type (local/livekit)

All data is anonymized, binned to prevent identification, and only sent with
explicit user opt-in. The telemetry ID is a random UUID with no connection to
user identity.
"""

from voice_mode.telemetry.collector import TelemetryCollector
from voice_mode.telemetry.privacy import (
    bin_duration,
    bin_size,
    anonymize_path,
    DurationBin,
    SizeBin
)
from voice_mode.telemetry.client import TelemetryClient
from voice_mode.telemetry.sender import (
    maybe_send_telemetry_background,
    maybe_send_telemetry_async,
    should_send_telemetry,
)

__all__ = [
    'TelemetryCollector',
    'TelemetryClient',
    'bin_duration',
    'bin_size',
    'anonymize_path',
    'DurationBin',
    'SizeBin',
    'maybe_send_telemetry_background',
    'maybe_send_telemetry_async',
    'should_send_telemetry',
]
