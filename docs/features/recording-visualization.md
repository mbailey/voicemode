# Recording Visualization

VoiceMode includes real-time visual feedback during voice recording sessions, making it easy to see when the system is listening, when speech is detected, and how close you are to the silence threshold.

## Features

The recording visualization provides:

- **Audio Level Meter**: Real-time display of microphone input levels (RMS)
- **Duration Counter**: Shows current recording time vs. maximum duration
- **Speech Detection Status**: Indicates whether speech has been detected
- **State Indicator**: Shows current recording state with visual cues:
  - 🔊 **WAITING** (yellow): Waiting for speech to begin
  - 🎤 **ACTIVE** (green): Speech detected, actively recording
  - ⏸️ **SILENCE** (blue): Silence after speech, counting down to stop
- **Silence Progress Bar**: Shows accumulation toward the silence threshold
- **Minimum Duration Progress**: Shows progress toward minimum recording duration

## Example Display

```
╭─────────────────────────────── 🎤 Recording... ───────────────────────────────╮
│                                                                              │
│     Duration:  3.2s / 120.0s                                                 │
│        State:  ACTIVE                                                        │
│       Speech:  ✓ Detected                                                    │
│  Audio Level:  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░  72%                │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## Configuration

The visualization is **enabled by default** but can be disabled if needed.

### Disable Visualization

To disable the visualization, set the environment variable:

```bash
export VOICEMODE_RECORDING_VISUALIZATION=false
```

Or add to your `.voicemode.env` file:

```bash
VOICEMODE_RECORDING_VISUALIZATION=false
```

### Enable Visualization (Default)

```bash
export VOICEMODE_RECORDING_VISUALIZATION=true
```

## Use Cases

### Why Use Visualization?

1. **Confidence**: See that the microphone is picking up your voice
2. **Timing**: Know when to start and stop speaking
3. **Troubleshooting**: Diagnose audio input issues quickly
4. **Awareness**: Understand when the system will automatically stop recording

### When to Disable

You might want to disable visualization if:

- Running in a script or automated environment
- Terminal doesn't support rich formatting
- You prefer minimal output
- Using VoiceMode programmatically

## Technical Details

### Implementation

The visualization uses the [Rich](https://github.com/Textualize/rich) library for terminal rendering and updates in real-time at 10 FPS during recording.

Key features:
- Thread-safe updates from audio callback
- Minimal performance impact
- Graceful degradation if Rich is not available
- Proper cleanup on errors or interruption

### Audio Level Calculation

Audio levels are calculated using RMS (Root Mean Square) of the audio samples and normalized to a 0-100% scale:

- **0-30%**: Low/background noise (red)
- **30-70%**: Normal speech levels (yellow)
- **70-100%**: Loud speech (green)

### State Machine

The visualization reflects the internal VAD (Voice Activity Detection) state machine:

1. **WAITING**: System is listening but hasn't detected speech yet
   - No timeout in this state
   - Waiting for voice activity to begin

2. **ACTIVE**: Speech has been detected
   - Recording is actively capturing your voice
   - Silence counter is reset when speech continues

3. **SILENCE**: Speech has stopped
   - Accumulating silence duration
   - Will stop recording when silence threshold is reached (default: 1000ms)
   - Only applies after minimum duration is met

## Related Configuration

These settings affect the recording behavior shown in the visualization:

```bash
# Maximum recording duration (default: 120s)
VOICEMODE_DEFAULT_LISTEN_DURATION=120.0

# Silence threshold before stopping (default: 1000ms)
VOICEMODE_SILENCE_THRESHOLD_MS=1000

# Minimum recording duration (default: 0.5s)
VOICEMODE_MIN_RECORDING_DURATION=0.5

# VAD aggressiveness 0-3 (default: 2)
VOICEMODE_VAD_AGGRESSIVENESS=2

# Disable silence detection entirely
VOICEMODE_DISABLE_SILENCE_DETECTION=false
```

## Troubleshooting

### Visualization Not Appearing

1. Check that visualization is enabled:
   ```bash
   voicemode config get VOICEMODE_RECORDING_VISUALIZATION
   ```

2. Ensure Rich library is installed:
   ```bash
   uv pip list | grep rich
   ```

3. Verify terminal supports Rich formatting (most modern terminals do)

### Audio Level Always Low

If the audio level meter shows very low levels:

1. Check microphone permissions
2. Verify correct input device is selected
3. Test microphone with system settings
4. Check microphone volume/gain settings

### Audio Level Always High

If the audio level meter shows constant high levels:

1. Check for background noise
2. Lower microphone gain
3. Move away from noise sources
4. Use a noise-cancelling microphone

## Future Enhancements

Potential future additions:

- Waveform visualization
- Spectral display
- Frequency analysis
- Audio history graph
- Customizable themes
- Terminal UI (TUI) mode with keyboard controls

## See Also

- [Voice Activity Detection (VAD)](vad.md)
- [Configuration Guide](../configuration.md)
- [Troubleshooting Audio Issues](../troubleshooting/audio.md)
