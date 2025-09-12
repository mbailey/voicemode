#!/usr/bin/env python3
"""
MPV Controller for Voice Mode
Uses python-mpv-jsonipc for IPC control of MPV player
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Will use python-mpv-jsonipc
# Install with: pip install python-mpv-jsonipc

@dataclass
class Chapter:
    """Represents a chapter/cue point in media"""
    title: str
    time: float  # Time in seconds
    
@dataclass 
class PlaybackState:
    """Current playback state"""
    playing: bool
    position: float
    duration: float
    volume: int
    filename: Optional[str] = None
    

class MPVController:
    """
    Controls MPV player via JSON IPC for Voice Mode audio playback
    """
    
    def __init__(self, socket_path: str = "/tmp/voicemode-mpv.sock"):
        self.socket_path = socket_path
        self.mpv = None
        self.chapters: List[Chapter] = []
        self.is_connected = False
        
        # Volume levels
        self.normal_volume = 70
        self.ducked_volume = 30
        
        # Logging
        self.logger = logging.getLogger(__name__)
        
    def start(self):
        """Start MPV instance with IPC server"""
        try:
            from python_mpv_jsonipc import MPV
            
            # Start MPV with our socket
            self.mpv = MPV(
                ipc_socket=self.socket_path,
                # Audio-only settings
                video=False,
                ytdl=True,  # Enable youtube-dl for streaming
                volume=self.normal_volume,
                # Keep running after playback
                idle=True,
                # Terminal output
                terminal=False,
                really_quiet=True
            )
            
            self.is_connected = True
            self.logger.info(f"MPV started with IPC at {self.socket_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to start MPV: {e}")
            raise
            
    def connect_existing(self):
        """Connect to an already-running MPV instance"""
        try:
            from python_mpv_jsonipc import MPV
            
            self.mpv = MPV(
                start_mpv=False,
                ipc_socket=self.socket_path
            )
            
            self.is_connected = True
            self.logger.info(f"Connected to existing MPV at {self.socket_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to MPV: {e}")
            raise
            
    def play(self, source: str, start_position: float = 0):
        """
        Play a file or URL
        
        Args:
            source: File path or URL to play
            start_position: Start position in seconds
        """
        if not self.is_connected:
            self.start()
            
        self.mpv.play(source)
        
        if start_position > 0:
            self.seek(start_position)
            
        self.logger.info(f"Playing: {source}")
        
    def play_music_for_programming(self, episode: int):
        """
        Play a Music for Programming episode
        
        Args:
            episode: Episode number (1-70+)
        """
        # Music for Programming URLs follow a pattern
        url_map = {
            1: "https://datashat.net/music_for_programming_1-datassette.mp3",
            # Add more episodes as needed
        }
        
        if episode in url_map:
            self.play(url_map[episode])
        else:
            # Try to construct URL (pattern may vary)
            url = f"https://datashat.net/music_for_programming_{episode}.mp3"
            self.play(url)
            
    def pause(self):
        """Pause playback"""
        if self.mpv:
            self.mpv.pause = True
            self.logger.info("Playback paused")
            
    def resume(self):
        """Resume playback"""
        if self.mpv:
            self.mpv.pause = False
            self.logger.info("Playback resumed")
            
    def stop(self):
        """Stop playback"""
        if self.mpv:
            self.mpv.stop()
            self.logger.info("Playback stopped")
            
    def seek(self, position: float):
        """
        Seek to position in seconds
        
        Args:
            position: Position in seconds
        """
        if self.mpv:
            self.mpv.seek(position, reference="absolute")
            self.logger.info(f"Seeked to {position}s")
            
    def seek_chapter(self, chapter: str):
        """
        Seek to a named chapter
        
        Args:
            chapter: Chapter title to seek to
        """
        for ch in self.chapters:
            if ch.title.lower() == chapter.lower():
                self.seek(ch.time)
                return
                
        self.logger.warning(f"Chapter not found: {chapter}")
        
    def next_chapter(self):
        """Skip to next chapter"""
        if self.mpv:
            self.mpv.command("add", "chapter", 1)
            
    def previous_chapter(self):
        """Go to previous chapter"""
        if self.mpv:
            self.mpv.command("add", "chapter", -1)
            
    def set_volume(self, level: int):
        """
        Set volume level
        
        Args:
            level: Volume level (0-100)
        """
        if self.mpv:
            self.mpv.volume = max(0, min(100, level))
            self.logger.info(f"Volume set to {level}")
            
    def duck_volume(self):
        """Lower volume for speech (ducking)"""
        if self.mpv:
            self.mpv.volume = self.ducked_volume
            self.logger.debug("Volume ducked for speech")
            
    def restore_volume(self):
        """Restore normal volume after speech"""
        if self.mpv:
            self.mpv.volume = self.normal_volume
            self.logger.debug("Volume restored")
            
    def get_state(self) -> PlaybackState:
        """Get current playback state"""
        if not self.mpv:
            return PlaybackState(False, 0, 0, 0)
            
        try:
            return PlaybackState(
                playing=not self.mpv.pause,
                position=self.mpv.time_pos or 0,
                duration=self.mpv.duration or 0,
                volume=self.mpv.volume,
                filename=self.mpv.filename
            )
        except:
            return PlaybackState(False, 0, 0, 0)
            
    def load_chapters(self, chapters: List[Chapter]):
        """
        Load chapter markers
        
        Args:
            chapters: List of Chapter objects
        """
        self.chapters = chapters
        self.logger.info(f"Loaded {len(chapters)} chapters")
        
    def load_chapters_from_file(self, filepath: str):
        """
        Load chapters from a JSON file
        
        Args:
            filepath: Path to JSON chapter file
        """
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        self.chapters = [
            Chapter(ch['title'], ch['time'])
            for ch in data.get('chapters', [])
        ]
        
        self.logger.info(f"Loaded {len(self.chapters)} chapters from {filepath}")
        
    def cleanup(self):
        """Clean up MPV instance"""
        if self.mpv:
            try:
                self.mpv.quit()
            except:
                pass
            self.mpv = None
            self.is_connected = False
            

# Voice Mode Integration Functions

def play_tts_output(controller: MPVController, audio_file: str):
    """Play TTS output with ducking"""
    controller.duck_volume()
    controller.play(audio_file)
    # Restore volume after TTS completes
    # (In practice, would need to monitor playback completion)
    time.sleep(2)  # Placeholder
    controller.restore_volume()
    

def play_tool_sound(controller: MPVController, tool_name: str):
    """Play sound effect for tool usage"""
    sound_map = {
        'bash': '/path/to/bash.wav',
        'grep': '/path/to/grep.wav',
        # etc...
    }
    
    if tool_name in sound_map:
        controller.play(sound_map[tool_name])
        

# Demo/Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    controller = MPVController()
    
    print("MPV Controller Demo")
    print("=" * 40)
    
    # Start MPV
    controller.start()
    
    # Example: Play a test file
    # controller.play("/path/to/audio.mp3")
    
    # Example: Play Music for Programming
    # controller.play_music_for_programming(1)
    
    # Example: Control playback
    # controller.set_volume(80)
    # controller.pause()
    # controller.resume()
    
    print("\nController ready. MPV instance running.")
    print("Socket path:", controller.socket_path)
    
    # Keep running for demo
    try:
        input("\nPress Enter to quit...")
    finally:
        controller.cleanup()