"""Real-time visualization for voice recording with silence detection."""

import threading
from typing import Optional
from datetime import datetime

import numpy as np
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich import box


class RecordingVisualizer:
    """
    Provides real-time visual feedback during voice recording.

    Displays:
    - Audio level meter (RMS visualization)
    - Recording duration
    - Speech detection status
    - Silence threshold progress
    """

    def __init__(
        self,
        max_duration: float,
        silence_threshold_ms: float,
        min_duration: float = 0.0,
        enabled: bool = True
    ):
        """
        Initialize the recording visualizer.

        Args:
            max_duration: Maximum recording duration in seconds
            silence_threshold_ms: Silence threshold in milliseconds
            min_duration: Minimum recording duration before silence can stop recording
            enabled: Whether visualization is enabled
        """
        self.enabled = enabled
        if not enabled:
            return

        self.max_duration = max_duration
        self.silence_threshold_ms = silence_threshold_ms
        self.min_duration = min_duration

        # Recording state
        self.recording_duration = 0.0
        self.silence_duration_ms = 0.0
        self.audio_level = 0.0
        self.speech_detected = False
        self.state = "WAITING"  # WAITING, ACTIVE, SILENCE

        # Thread safety
        self._lock = threading.Lock()

        # Rich console
        self.console = Console()
        self.live: Optional[Live] = None

    def start(self):
        """Start the live display."""
        if not self.enabled:
            return

        self.live = Live(
            self._create_display(),
            console=self.console,
            refresh_per_second=10,
            transient=False
        )
        self.live.start()

    def stop(self):
        """Stop the live display."""
        if not self.enabled or not self.live:
            return

        self.live.stop()

    def update(
        self,
        duration: float,
        audio_level: float,
        speech_detected: bool,
        silence_ms: float,
        state: str
    ):
        """
        Update the visualization with current recording state.

        Args:
            duration: Current recording duration in seconds
            audio_level: Current audio RMS level
            speech_detected: Whether speech has been detected at all
            silence_ms: Current silence duration in milliseconds
            state: Current recording state (WAITING, ACTIVE, SILENCE)
        """
        if not self.enabled or not self.live:
            return

        with self._lock:
            self.recording_duration = duration
            self.audio_level = audio_level
            self.speech_detected = speech_detected
            self.silence_duration_ms = silence_ms
            self.state = state

        # Update display
        try:
            self.live.update(self._create_display())
        except Exception:
            # Silently ignore display update errors
            pass

    def _create_display(self) -> Panel:
        """Create the rich display panel."""
        with self._lock:
            duration = self.recording_duration
            level = self.audio_level
            speech = self.speech_detected
            silence_ms = self.silence_duration_ms
            state = self.state

        # Create main table
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column()

        # Duration
        duration_text = f"{duration:.1f}s / {self.max_duration:.1f}s"
        table.add_row("Duration:", duration_text)

        # State indicator with color
        state_colors = {
            "WAITING": "yellow",
            "ACTIVE": "green",
            "SILENCE": "blue"
        }
        state_color = state_colors.get(state, "white")
        state_text = Text(state, style=f"bold {state_color}")
        table.add_row("State:", state_text)

        # Speech detected
        speech_icon = "✓" if speech else "✗"
        speech_style = "green" if speech else "dim"
        table.add_row("Speech:", Text(f"{speech_icon} Detected" if speech else f"{speech_icon} Not yet", style=speech_style))

        # Audio level meter
        level_bar = self._create_level_bar(level)
        table.add_row("Audio Level:", level_bar)

        # Silence progress (only show if speech was detected)
        if speech and state == "SILENCE":
            silence_bar = self._create_silence_bar(silence_ms)
            table.add_row("Silence:", silence_bar)

        # Min duration progress (only show before min duration is reached)
        if duration < self.min_duration:
            min_duration_bar = self._create_min_duration_bar(duration)
            table.add_row("Min Duration:", min_duration_bar)

        # Panel title with emoji
        title_emoji = "🎤" if state == "ACTIVE" else "⏸️" if state == "SILENCE" else "🔊"
        title = f"{title_emoji} Recording..."

        return Panel(
            table,
            title=title,
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2)
        )

    def _create_level_bar(self, level: float) -> Text:
        """Create audio level bar visualization."""
        # Normalize level to 0-100 range (RMS values typically 0-3000)
        normalized = min(100, (level / 30.0))
        bar_length = 40
        filled = int((normalized / 100) * bar_length)

        # Color based on level
        if normalized > 70:
            color = "green"
        elif normalized > 30:
            color = "yellow"
        else:
            color = "red"

        bar = "▓" * filled + "░" * (bar_length - filled)
        return Text(f"{bar} {normalized:3.0f}%", style=color)

    def _create_silence_bar(self, silence_ms: float) -> Text:
        """Create silence progress bar."""
        progress = min(100, (silence_ms / self.silence_threshold_ms) * 100)
        bar_length = 40
        filled = int((progress / 100) * bar_length)

        # Color based on proximity to threshold
        if progress > 80:
            color = "red"
        elif progress > 50:
            color = "yellow"
        else:
            color = "blue"

        bar = "▓" * filled + "░" * (bar_length - filled)
        return Text(f"{bar} {silence_ms:.0f}ms / {self.silence_threshold_ms:.0f}ms", style=color)

    def _create_min_duration_bar(self, duration: float) -> Text:
        """Create minimum duration progress bar."""
        progress = min(100, (duration / self.min_duration) * 100)
        bar_length = 40
        filled = int((progress / 100) * bar_length)

        bar = "▓" * filled + "░" * (bar_length - filled)
        return Text(f"{bar} {duration:.1f}s / {self.min_duration:.1f}s", style="cyan")


def create_visualizer(
    max_duration: float,
    silence_threshold_ms: float,
    min_duration: float = 0.0,
    enabled: bool = True
) -> RecordingVisualizer:
    """
    Factory function to create a recording visualizer.

    Args:
        max_duration: Maximum recording duration in seconds
        silence_threshold_ms: Silence threshold in milliseconds
        min_duration: Minimum recording duration
        enabled: Whether visualization is enabled

    Returns:
        RecordingVisualizer instance
    """
    return RecordingVisualizer(
        max_duration=max_duration,
        silence_threshold_ms=silence_threshold_ms,
        min_duration=min_duration,
        enabled=enabled
    )
