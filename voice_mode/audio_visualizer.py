"""Audio level visualization for terminal display."""

import sys
import time
import threading
import numpy as np
from typing import Optional, List
from collections import deque
import math


class AudioLevelVisualizer:
    """Terminal-based audio level visualization with bouncing bars."""
    
    def __init__(self, num_bars: int = 20, max_height: int = 8):
        """Initialize the audio visualizer.
        
        Args:
            num_bars: Number of bars to display
            max_height: Maximum height of bars in characters
        """
        self.num_bars = num_bars
        self.max_height = max_height
        self.levels = deque([0.0] * num_bars, maxlen=num_bars)
        self.peak_levels = [0.0] * num_bars
        self.peak_hold_frames = [0] * num_bars
        self.running = False
        self.display_thread = None
        self.last_update = time.time()
        self.lock = threading.Lock()
        
        # Bar characters for smooth animation
        self.bar_chars = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
        self.peak_char = '▪'
        
        # Color codes for different levels
        self.colors = {
            'low': '\033[92m',      # Green
            'mid': '\033[93m',      # Yellow
            'high': '\033[91m',     # Red
            'peak': '\033[95m',     # Magenta
            'reset': '\033[0m'
        }
        
        # Audio processing
        self.smoothing_factor = 0.3  # Lower = smoother
        self.decay_rate = 0.95       # How fast bars fall
        self.peak_hold_time = 20     # Frames to hold peak
        
    def start(self):
        """Start the visualization display thread."""
        if self.running:
            return
            
        self.running = True
        self.display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self.display_thread.start()
        
        # Hide cursor for cleaner display
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()
        
    def stop(self):
        """Stop the visualization display."""
        self.running = False
        if self.display_thread:
            self.display_thread.join(timeout=1.0)
            
        # Show cursor again
        sys.stdout.write('\033[?25h')
        # Clear the visualization line
        sys.stdout.write('\r' + ' ' * (self.num_bars * 2 + 20) + '\r')
        sys.stdout.flush()
        
    def update_level(self, audio_level: float, frequency_data: Optional[List[float]] = None):
        """Update the audio level display.
        
        Args:
            audio_level: Overall audio level (0.0 to 1.0)
            frequency_data: Optional frequency band data for spectrum display
        """
        with self.lock:
            current_time = time.time()
            
            if frequency_data and len(frequency_data) >= self.num_bars:
                # Use frequency data for spectrum analyzer effect
                for i in range(self.num_bars):
                    # Smooth the transition
                    target = frequency_data[i]
                    current = self.levels[i]
                    self.levels[i] = current + (target - current) * self.smoothing_factor
                    
                    # Update peak hold
                    if self.levels[i] > self.peak_levels[i]:
                        self.peak_levels[i] = self.levels[i]
                        self.peak_hold_frames[i] = self.peak_hold_time
            else:
                # Simple VU meter mode - all bars show same level with slight variation
                for i in range(self.num_bars):
                    # Add some variation for visual interest
                    variation = 0.1 * math.sin(current_time * 10 + i * 0.5)
                    target = min(1.0, max(0.0, audio_level + variation * audio_level))
                    
                    # Smooth the transition
                    current = self.levels[i]
                    self.levels[i] = current + (target - current) * self.smoothing_factor
                    
                    # Update peak hold
                    if self.levels[i] > self.peak_levels[i]:
                        self.peak_levels[i] = self.levels[i]
                        self.peak_hold_frames[i] = self.peak_hold_time
            
            self.last_update = current_time
            
    def _display_loop(self):
        """Main display loop running in separate thread."""
        while self.running:
            self._render()
            time.sleep(0.05)  # 20 FPS
            
            # Apply decay when no updates
            with self.lock:
                current_time = time.time()
                if current_time - self.last_update > 0.1:
                    # Decay the levels
                    for i in range(self.num_bars):
                        self.levels[i] *= self.decay_rate
                        
                        # Decay peak hold
                        if self.peak_hold_frames[i] > 0:
                            self.peak_hold_frames[i] -= 1
                        else:
                            self.peak_levels[i] *= 0.98
                            
    def _render(self):
        """Render the current audio levels to terminal."""
        with self.lock:
            # Build the display string
            display = '\r🎵 '
            
            for i, level in enumerate(self.levels):
                # Calculate bar height
                height = int(level * self.max_height)
                
                if height == 0:
                    # Empty bar
                    display += '  '
                else:
                    # Choose color based on level
                    if level > 0.8:
                        color = self.colors['high']
                    elif level > 0.5:
                        color = self.colors['mid']
                    else:
                        color = self.colors['low']
                    
                    # Select bar character
                    char_idx = min(height - 1, len(self.bar_chars) - 1)
                    bar_char = self.bar_chars[char_idx]
                    
                    # Add peak indicator if applicable
                    peak_height = int(self.peak_levels[i] * self.max_height)
                    if peak_height > height and self.peak_hold_frames[i] > 0:
                        display += color + bar_char + self.colors['peak'] + self.peak_char + self.colors['reset']
                    else:
                        display += color + bar_char + self.colors['reset'] + ' '
            
            # Add overall level indicator
            avg_level = sum(self.levels) / len(self.levels) if self.levels else 0
            level_pct = int(avg_level * 100)
            display += f' {level_pct:3d}% '
            
            # Write to terminal
            sys.stdout.write(display)
            sys.stdout.flush()


class WhisperStreamVisualizer:
    """Audio visualizer that monitors WhisperStream's audio input."""
    
    def __init__(self, visualizer: Optional[AudioLevelVisualizer] = None):
        """Initialize the WhisperStream audio monitor.
        
        Args:
            visualizer: Optional custom visualizer, creates default if None
        """
        self.visualizer = visualizer or AudioLevelVisualizer(num_bars=15, max_height=6)
        self.monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self, audio_callback=None):
        """Start monitoring audio levels.
        
        Args:
            audio_callback: Optional callback that provides audio data
        """
        if self.monitoring:
            return
            
        self.monitoring = True
        self.visualizer.start()
        
        if audio_callback:
            # Use provided callback for audio data
            self.audio_callback = audio_callback
        else:
            # Create a simple simulator for testing
            self._start_simulated_audio()
            
    def stop_monitoring(self):
        """Stop monitoring audio levels."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
        self.visualizer.stop()
        
    def _start_simulated_audio(self):
        """Start simulated audio for testing without actual audio input."""
        def simulate():
            import random
            while self.monitoring:
                # Simulate audio levels with some patterns
                base_level = 0.2 + 0.3 * abs(math.sin(time.time() * 0.5))
                
                # Add random spikes (simulating speech)
                if random.random() > 0.9:
                    base_level = min(1.0, base_level + random.random() * 0.5)
                    
                # Generate frequency-like data
                freq_data = []
                for i in range(self.visualizer.num_bars):
                    # Create a spectrum-like pattern
                    freq = base_level * (1.0 - i / self.visualizer.num_bars)
                    freq += random.random() * 0.1
                    freq = max(0.0, min(1.0, freq))
                    freq_data.append(freq)
                    
                self.visualizer.update_level(base_level, freq_data)
                time.sleep(0.05)
                
        self.monitor_thread = threading.Thread(target=simulate, daemon=True)
        self.monitor_thread.start()
        
    def update_from_audio_data(self, audio_data: np.ndarray, sample_rate: int = 16000):
        """Update visualization from raw audio data.
        
        Args:
            audio_data: Audio samples as numpy array
            sample_rate: Sample rate of the audio
        """
        if not self.monitoring:
            return
            
        # Calculate RMS level
        rms = np.sqrt(np.mean(audio_data**2))
        # Normalize to 0-1 range (assuming 16-bit audio range)
        level = min(1.0, rms * 10)  # Adjust multiplier for sensitivity
        
        # Optional: Calculate frequency spectrum for more detailed visualization
        try:
            # Simple FFT for frequency analysis
            fft = np.fft.rfft(audio_data)
            freqs = np.abs(fft)
            
            # Bin frequencies into bands for visualization
            num_bands = self.visualizer.num_bars
            band_size = len(freqs) // num_bands
            freq_data = []
            
            for i in range(num_bands):
                start = i * band_size
                end = start + band_size
                band_level = np.mean(freqs[start:end])
                # Normalize (adjust scale factor as needed)
                band_level = min(1.0, band_level / 1000)
                freq_data.append(band_level)
                
            self.visualizer.update_level(level, freq_data)
        except:
            # Fallback to simple level display
            self.visualizer.update_level(level)


def demo_visualizer():
    """Demo function to test the visualizer."""
    print("Audio Level Visualizer Demo")
    print("Press Ctrl+C to stop\n")
    
    visualizer = AudioLevelVisualizer(num_bars=20, max_height=8)
    monitor = WhisperStreamVisualizer(visualizer)
    
    try:
        monitor.start_monitoring()
        print("Monitoring audio levels...\n")
        
        # Keep running until interrupted
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\nStopping visualizer...")
        monitor.stop_monitoring()
        print("Demo ended.")


if __name__ == "__main__":
    demo_visualizer()