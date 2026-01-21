"""macOS VoiceProcessingIO microphone capture for mic mode support.

This module uses ctypes to call CoreAudio's VoiceProcessingIO audio unit directly,
which enables macOS mic modes (Voice Isolation, Wide Spectrum, Standard) in Control Center.

The module gracefully handles non-macOS platforms by setting _AVAILABLE = False,
allowing imports to succeed on all platforms while functionality is gated by is_available().
"""

import ctypes
from ctypes import (
    c_void_p, c_uint32, c_int32, c_double, c_float, c_uint8,
    POINTER, Structure, CFUNCTYPE, byref, cast, sizeof,
)
import logging
import platform
import time
from typing import Tuple, Optional
import numpy as np

logger = logging.getLogger("voicemode")

# Module availability flag - set during framework loading
_AVAILABLE = False
_at = None
_cf = None

# Only attempt to load frameworks on macOS
if platform.system() == "Darwin":
    try:
        _at = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox')
        _cf = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        _AVAILABLE = True
    except OSError as e:
        logger.debug(f"Failed to load CoreAudio frameworks: {e}")

# Constants (platform-independent values)
_kAudioUnitType_Output = 0x61756f75  # 'auou'
_kAudioUnitSubType_VoiceProcessingIO = 0x7670696f  # 'vpio'
_kAudioUnitManufacturer_Apple = 0x6170706c  # 'appl'
_kAudioUnitScope_Global = 0
_kAudioUnitScope_Output = 2
_kAudioOutputUnitProperty_SetInputCallback = 2005
_kAudioUnitProperty_StreamFormat = 8

# This requires _cf to be loaded
_kCFRunLoopDefaultMode = None
if _AVAILABLE:
    _kCFRunLoopDefaultMode = c_void_p.in_dll(_cf, 'kCFRunLoopDefaultMode')


class _AudioComponentDescription(Structure):
    _fields_ = [
        ('componentType', c_uint32),
        ('componentSubType', c_uint32),
        ('componentManufacturer', c_uint32),
        ('componentFlags', c_uint32),
        ('componentFlagsMask', c_uint32),
    ]


class _AudioStreamBasicDescription(Structure):
    _fields_ = [
        ('mSampleRate', c_double),
        ('mFormatID', c_uint32),
        ('mFormatFlags', c_uint32),
        ('mBytesPerPacket', c_uint32),
        ('mFramesPerPacket', c_uint32),
        ('mBytesPerFrame', c_uint32),
        ('mChannelsPerFrame', c_uint32),
        ('mBitsPerChannel', c_uint32),
        ('mReserved', c_uint32),
    ]


class _AudioBuffer(Structure):
    _fields_ = [
        ('mNumberChannels', c_uint32),
        ('mDataByteSize', c_uint32),
        ('mData', c_void_p),
    ]


class _AudioBufferList(Structure):
    _fields_ = [
        ('mNumberBuffers', c_uint32),
        ('mBuffers', _AudioBuffer * 1),
    ]


class _AudioTimeStamp(Structure):
    _fields_ = [
        ('mSampleTime', c_double),
        ('mHostTime', ctypes.c_uint64),
        ('mRateScalar', c_double),
        ('mWordClockTime', ctypes.c_uint64),
        ('mSMPTETime', c_uint8 * 24),
        ('mFlags', c_uint32),
        ('mReserved', c_uint32),
    ]


_AURenderCallback = CFUNCTYPE(
    c_int32, c_void_p, POINTER(c_uint32), POINTER(_AudioTimeStamp),
    c_uint32, c_uint32, POINTER(_AudioBufferList),
)


class _AURenderCallbackStruct(Structure):
    _fields_ = [
        ('inputProc', _AURenderCallback),
        ('inputProcRefCon', c_void_p),
    ]


# Function signatures (only set when frameworks are available)
if _AVAILABLE:
    _at.AudioComponentFindNext.argtypes = [c_void_p, POINTER(_AudioComponentDescription)]
    _at.AudioComponentFindNext.restype = c_void_p
    _at.AudioComponentInstanceNew.argtypes = [c_void_p, POINTER(c_void_p)]
    _at.AudioComponentInstanceNew.restype = c_int32
    _at.AudioComponentInstanceDispose.argtypes = [c_void_p]
    _at.AudioComponentInstanceDispose.restype = c_int32
    _at.AudioUnitInitialize.argtypes = [c_void_p]
    _at.AudioUnitInitialize.restype = c_int32
    _at.AudioOutputUnitStart.argtypes = [c_void_p]
    _at.AudioOutputUnitStart.restype = c_int32
    _at.AudioOutputUnitStop.argtypes = [c_void_p]
    _at.AudioOutputUnitStop.restype = c_int32
    _at.AudioUnitGetProperty.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_void_p, POINTER(c_uint32)]
    _at.AudioUnitGetProperty.restype = c_int32
    _at.AudioUnitSetProperty.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_void_p, c_uint32]
    _at.AudioUnitSetProperty.restype = c_int32
    _at.AudioUnitRender.argtypes = [c_void_p, POINTER(c_uint32), POINTER(_AudioTimeStamp), c_uint32, c_uint32, POINTER(_AudioBufferList)]
    _at.AudioUnitRender.restype = c_int32
    _cf.CFRunLoopGetCurrent.argtypes = []
    _cf.CFRunLoopGetCurrent.restype = c_void_p
    _cf.CFRunLoopRunInMode.argtypes = [c_void_p, c_double, ctypes.c_bool]
    _cf.CFRunLoopRunInMode.restype = c_int32


class VoiceProcessingRecorder:
    """Records audio using macOS VoiceProcessingIO, enabling system mic modes."""

    def __init__(self):
        self._audio_unit = None
        self._sample_rate = 48000.0  # Will be updated to native rate
        self._audio_chunks: list = []
        self._is_running = False
        self._callback = None
        self._speech_detected = False
        self._silence_ms = 0.0

    def _create_callback(self, vad_threshold: float, silence_threshold_ms: int, min_duration: float):
        audio_unit = self._audio_unit
        start_time = time.time()

        def callback(ref_con, action_flags, timestamp, bus_number, num_frames, io_data):
            if not self._is_running:
                return 0

            buffer_size = num_frames * 4
            buffer = (c_float * num_frames)()

            buffer_list = _AudioBufferList()
            buffer_list.mNumberBuffers = 1
            buffer_list.mBuffers[0].mNumberChannels = 1
            buffer_list.mBuffers[0].mDataByteSize = buffer_size
            buffer_list.mBuffers[0].mData = cast(buffer, c_void_p)

            status = _at.AudioUnitRender(
                audio_unit, action_flags, timestamp,
                bus_number, num_frames, byref(buffer_list)
            )

            if status != 0:
                return 0

            samples = np.frombuffer(buffer, dtype=np.float32).copy()
            self._audio_chunks.append(samples)

            # VAD: calculate RMS energy
            energy = np.sqrt(np.mean(samples ** 2))
            buffer_duration_ms = (num_frames / self._sample_rate) * 1000

            if energy >= vad_threshold:
                self._speech_detected = True
                self._silence_ms = 0
            elif self._speech_detected:
                self._silence_ms += buffer_duration_ms
                elapsed = time.time() - start_time
                if self._silence_ms >= silence_threshold_ms and elapsed >= min_duration:
                    self._is_running = False

            return 0

        self._callback = _AURenderCallback(callback)
        return self._callback

    def record(
        self,
        max_duration: float = 120.0,
        min_duration: float = 2.0,
        silence_threshold_ms: int = 1000,
        vad_aggressiveness: int = 2,
    ) -> Tuple[np.ndarray, bool, int]:
        """Record audio with VAD-based silence detection.

        Args:
            max_duration: Maximum recording duration in seconds
            min_duration: Minimum duration before silence detection can stop
            silence_threshold_ms: Silence duration to trigger stop
            vad_aggressiveness: 0-3, higher = stricter speech detection.
                Unlike webrtcvad which uses a neural model, this uses simple
                RMS energy thresholds: 0=0.002, 1=0.005, 2=0.01, 3=0.02.
                Higher values require louder speech to trigger detection.

        Returns:
            Tuple of (audio_samples, speech_detected, sample_rate)
        """
        # Energy-based VAD thresholds (RMS values, not webrtcvad aggressiveness)
        # These map the 0-3 scale to energy levels for simple threshold detection
        vad_thresholds = {0: 0.002, 1: 0.005, 2: 0.01, 3: 0.02}
        vad_threshold = vad_thresholds.get(vad_aggressiveness, 0.01)

        self._audio_chunks = []
        self._speech_detected = False
        self._silence_ms = 0

        # Create VoiceProcessingIO audio unit
        desc = _AudioComponentDescription(
            componentType=_kAudioUnitType_Output,
            componentSubType=_kAudioUnitSubType_VoiceProcessingIO,
            componentManufacturer=_kAudioUnitManufacturer_Apple,
            componentFlags=0,
            componentFlagsMask=0,
        )

        component = _at.AudioComponentFindNext(None, byref(desc))
        if not component:
            raise RuntimeError("VoiceProcessingIO not available")

        instance = c_void_p()
        status = _at.AudioComponentInstanceNew(component, byref(instance))
        if status != 0:
            raise RuntimeError(f"Failed to create audio unit: {status}")
        self._audio_unit = instance.value

        # Get native sample rate (don't try to change it - causes init failures)
        stream_format = _AudioStreamBasicDescription()
        prop_size = c_uint32(sizeof(_AudioStreamBasicDescription))
        status = _at.AudioUnitGetProperty(
            self._audio_unit, _kAudioUnitProperty_StreamFormat,
            _kAudioUnitScope_Output, 1, byref(stream_format), byref(prop_size)
        )
        if status == 0:
            self._sample_rate = stream_format.mSampleRate
            logger.debug(f"VoiceProcessingIO native sample rate: {self._sample_rate} Hz")

        # Set callback
        callback = self._create_callback(vad_threshold, silence_threshold_ms, min_duration)
        callback_struct = _AURenderCallbackStruct(inputProc=callback, inputProcRefCon=None)
        status = _at.AudioUnitSetProperty(
            self._audio_unit, _kAudioOutputUnitProperty_SetInputCallback,
            _kAudioUnitScope_Global, 0, byref(callback_struct), sizeof(_AURenderCallbackStruct)
        )
        if status != 0:
            self._cleanup()
            raise RuntimeError(f"Failed to set callback: {status}")

        # Initialize and start
        status = _at.AudioUnitInitialize(self._audio_unit)
        if status != 0:
            self._cleanup()
            raise RuntimeError(f"Failed to initialize: {status}")

        self._is_running = True
        status = _at.AudioOutputUnitStart(self._audio_unit)
        if status != 0:
            self._cleanup()
            raise RuntimeError(f"Failed to start: {status}")

        logger.info("Recording with VoiceProcessingIO (mic modes enabled)")

        # Run loop
        start_time = time.time()
        try:
            while self._is_running and (time.time() - start_time) < max_duration:
                _cf.CFRunLoopRunInMode(_kCFRunLoopDefaultMode, 0.05, False)
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

        # Combine audio chunks
        if self._audio_chunks:
            audio = np.concatenate(self._audio_chunks)
        else:
            audio = np.array([], dtype=np.float32)

        return audio, self._speech_detected, int(self._sample_rate)

    def _cleanup(self):
        self._is_running = False
        if self._audio_unit:
            _at.AudioOutputUnitStop(self._audio_unit)
            _at.AudioComponentInstanceDispose(self._audio_unit)
            self._audio_unit = None


def is_available() -> bool:
    """Check if VoiceProcessingIO is available on this system."""
    if not _AVAILABLE:
        return False

    try:
        desc = _AudioComponentDescription(
            componentType=_kAudioUnitType_Output,
            componentSubType=_kAudioUnitSubType_VoiceProcessingIO,
            componentManufacturer=_kAudioUnitManufacturer_Apple,
            componentFlags=0,
            componentFlagsMask=0,
        )
        component = _at.AudioComponentFindNext(None, byref(desc))
        return component is not None
    except Exception as e:
        logger.debug(f"VoiceProcessingIO availability check failed: {e}")
        return False


def record_audio(
    max_duration: float = 120.0,
    min_duration: float = 2.0,
    silence_threshold_ms: int = 1000,
    vad_aggressiveness: int = 2,
) -> Tuple[np.ndarray, bool, int]:
    """Record audio using VoiceProcessingIO with VAD.

    This enables macOS mic modes (Voice Isolation, Wide Spectrum, Standard).

    Args:
        max_duration: Maximum recording duration in seconds
        min_duration: Minimum duration before silence detection can stop
        silence_threshold_ms: Silence duration (ms) to trigger stop
        vad_aggressiveness: 0-3, higher = stricter speech detection

    Returns:
        Tuple of (audio_samples as float32, speech_detected, native_sample_rate)

    Raises:
        RuntimeError: If VoiceProcessingIO is not available
    """
    if not is_available():
        raise RuntimeError("VoiceProcessingIO is not available on this system")
    recorder = VoiceProcessingRecorder()
    return recorder.record(max_duration, min_duration, silence_threshold_ms, vad_aggressiveness)
