#!/usr/bin/env python3
"""
MCP Server for Audio Controller
Provides audio playback control via MCP tools for Voice Mode
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.types import Tool, TextContent

from .mpv_controller import MPVController, Chapter, PlaybackState

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global controller instance
controller: Optional[MPVController] = None


def get_controller() -> MPVController:
    """Get or create the MPV controller instance"""
    global controller
    if controller is None:
        controller = MPVController()
        controller.start()
    return controller


# MCP Server setup
server = Server("audio-controller")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available audio control tools"""
    return [
        Tool(
            name="play_audio",
            description="Play an audio file or stream from URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "File path or URL to play"
                    },
                    "start_position": {
                        "type": "number",
                        "description": "Start position in seconds (optional)",
                        "default": 0
                    }
                },
                "required": ["source"]
            }
        ),
        Tool(
            name="pause_audio",
            description="Pause audio playback",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="resume_audio", 
            description="Resume audio playback",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="stop_audio",
            description="Stop audio playback",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="set_volume",
            description="Set audio volume level",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Volume level (0-100)",
                        "minimum": 0,
                        "maximum": 100
                    }
                },
                "required": ["level"]
            }
        ),
        Tool(
            name="duck_volume",
            description="Lower volume for speech (ducking)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="restore_volume",
            description="Restore normal volume after speech",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="seek_audio",
            description="Seek to position in audio",
            inputSchema={
                "type": "object",
                "properties": {
                    "position": {
                        "type": "number",
                        "description": "Position in seconds"
                    }
                },
                "required": ["position"]
            }
        ),
        Tool(
            name="seek_chapter",
            description="Seek to a named chapter",
            inputSchema={
                "type": "object",
                "properties": {
                    "chapter": {
                        "type": "string",
                        "description": "Chapter name to seek to"
                    }
                },
                "required": ["chapter"]
            }
        ),
        Tool(
            name="next_chapter",
            description="Skip to next chapter",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="previous_chapter",
            description="Go to previous chapter",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_playback_state",
            description="Get current playback state",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="play_music_for_programming",
            description="Play a Music for Programming episode",
            inputSchema={
                "type": "object",
                "properties": {
                    "episode": {
                        "type": "integer",
                        "description": "Episode number (1-70+)",
                        "minimum": 1
                    }
                },
                "required": ["episode"]
            }
        ),
        Tool(
            name="load_chapters",
            description="Load chapter markers from JSON",
            inputSchema={
                "type": "object",
                "properties": {
                    "chapters": {
                        "type": "array",
                        "description": "Array of chapter objects with title and time",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "time": {"type": "number"}
                            },
                            "required": ["title", "time"]
                        }
                    }
                },
                "required": ["chapters"]
            }
        ),
        Tool(
            name="play_tts",
            description="Play TTS output with automatic volume ducking",
            inputSchema={
                "type": "object",
                "properties": {
                    "audio_file": {
                        "type": "string",
                        "description": "Path to TTS audio file"
                    },
                    "duck": {
                        "type": "boolean",
                        "description": "Whether to duck background audio",
                        "default": True
                    }
                },
                "required": ["audio_file"]
            }
        ),
        Tool(
            name="play_tool_sound",
            description="Play sound effect for tool usage",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Name of the tool that was triggered"
                    }
                },
                "required": ["tool_name"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute audio control tools"""
    ctrl = get_controller()
    
    try:
        if name == "play_audio":
            ctrl.play(
                arguments["source"],
                arguments.get("start_position", 0)
            )
            return [TextContent(
                type="text",
                text=f"Playing: {arguments['source']}"
            )]
            
        elif name == "pause_audio":
            ctrl.pause()
            return [TextContent(
                type="text",
                text="Audio paused"
            )]
            
        elif name == "resume_audio":
            ctrl.resume()
            return [TextContent(
                type="text",
                text="Audio resumed"
            )]
            
        elif name == "stop_audio":
            ctrl.stop()
            return [TextContent(
                type="text",
                text="Audio stopped"
            )]
            
        elif name == "set_volume":
            ctrl.set_volume(arguments["level"])
            return [TextContent(
                type="text",
                text=f"Volume set to {arguments['level']}"
            )]
            
        elif name == "duck_volume":
            ctrl.duck_volume()
            return [TextContent(
                type="text",
                text="Volume ducked for speech"
            )]
            
        elif name == "restore_volume":
            ctrl.restore_volume()
            return [TextContent(
                type="text",
                text="Volume restored"
            )]
            
        elif name == "seek_audio":
            ctrl.seek(arguments["position"])
            return [TextContent(
                type="text",
                text=f"Seeked to {arguments['position']}s"
            )]
            
        elif name == "seek_chapter":
            ctrl.seek_chapter(arguments["chapter"])
            return [TextContent(
                type="text",
                text=f"Seeked to chapter: {arguments['chapter']}"
            )]
            
        elif name == "next_chapter":
            ctrl.next_chapter()
            return [TextContent(
                type="text",
                text="Skipped to next chapter"
            )]
            
        elif name == "previous_chapter":
            ctrl.previous_chapter()
            return [TextContent(
                type="text",
                text="Went to previous chapter"
            )]
            
        elif name == "get_playback_state":
            state = ctrl.get_state()
            return [TextContent(
                type="text",
                text=json.dumps({
                    "playing": state.playing,
                    "position": state.position,
                    "duration": state.duration,
                    "volume": state.volume,
                    "filename": state.filename
                }, indent=2)
            )]
            
        elif name == "play_music_for_programming":
            ctrl.play_music_for_programming(arguments["episode"])
            return [TextContent(
                type="text",
                text=f"Playing Music for Programming episode {arguments['episode']}"
            )]
            
        elif name == "load_chapters":
            chapters = [
                Chapter(ch["title"], ch["time"])
                for ch in arguments["chapters"]
            ]
            ctrl.load_chapters(chapters)
            return [TextContent(
                type="text",
                text=f"Loaded {len(chapters)} chapters"
            )]
            
        elif name == "play_tts":
            if arguments.get("duck", True):
                ctrl.duck_volume()
            ctrl.play(arguments["audio_file"])
            # Note: In production, would monitor completion to restore volume
            return [TextContent(
                type="text",
                text=f"Playing TTS: {arguments['audio_file']}"
            )]
            
        elif name == "play_tool_sound":
            # Tool sound mapping (would be configurable)
            sound_map = {
                'bash': 'kick',
                'grep': 'hihat',
                'read': 'snare',
                'write': 'clap',
                'edit': 'cowbell'
            }
            
            tool = arguments["tool_name"]
            sound = sound_map.get(tool, 'click')
            
            # In production, would play actual sound file
            return [TextContent(
                type="text",
                text=f"Playing sound '{sound}' for tool '{tool}'"
            )]
            
        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]
            
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


async def main():
    """Main entry point for MCP server"""
    from mcp.server.stdio import stdio_server
    
    logger.info("Starting Audio Controller MCP Server")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())