#!/usr/bin/env python3
"""
CLI interface for the Audio Controller
Mirrors the MCP server commands for command-line control
"""

import click
import json
import sys
from pathlib import Path
from typing import Optional

from .mpv_controller import MPVController, Chapter

# Global controller instance
controller: Optional[MPVController] = None


def get_controller() -> MPVController:
    """Get or create the MPV controller instance"""
    global controller
    if controller is None:
        controller = MPVController()
        controller.start()
    return controller


@click.group(name='audio-control')
@click.option('--socket', '-s', default='/tmp/voicemode-mpv.sock',
              help='MPV IPC socket path')
@click.option('--connect/--start', '-c/-S', default=False,
              help='Connect to existing MPV or start new instance')
@click.pass_context
def cli(ctx, socket, connect):
    """Audio Controller CLI - Control MPV for Voice Mode
    
    This CLI mirrors the MCP server commands for audio control.
    """
    ctx.ensure_object(dict)
    ctx.obj['socket'] = socket
    ctx.obj['connect'] = connect
    
    # Initialize controller with socket path
    global controller
    controller = MPVController(socket_path=socket)
    
    if connect:
        try:
            controller.connect_existing()
            click.echo(f"Connected to existing MPV at {socket}")
        except:
            click.echo("No existing MPV found, starting new instance...")
            controller.start()
    else:
        controller.start()


@cli.command('play')
@click.argument('source')
@click.option('--position', '-p', type=float, default=0,
              help='Start position in seconds')
def play_audio(source, position):
    """Play an audio file or stream from URL"""
    ctrl = get_controller()
    ctrl.play(source, position)
    click.echo(f"Playing: {source}")
    if position > 0:
        click.echo(f"Starting at: {position}s")


@cli.command('pause')
def pause_audio():
    """Pause audio playback"""
    ctrl = get_controller()
    ctrl.pause()
    click.echo("Playback paused")


@cli.command('resume')
def resume_audio():
    """Resume audio playback"""
    ctrl = get_controller()
    ctrl.resume()
    click.echo("Playback resumed")


@cli.command('stop')
def stop_audio():
    """Stop audio playback"""
    ctrl = get_controller()
    ctrl.stop()
    click.echo("Playback stopped")


@cli.command('volume')
@click.argument('level', type=click.IntRange(0, 100))
def set_volume(level):
    """Set audio volume (0-100)"""
    ctrl = get_controller()
    ctrl.set_volume(level)
    click.echo(f"Volume set to {level}")


@cli.command('duck')
def duck_volume():
    """Lower volume for speech (ducking)"""
    ctrl = get_controller()
    ctrl.duck_volume()
    click.echo("Volume ducked for speech")


@cli.command('restore')
def restore_volume():
    """Restore normal volume after speech"""
    ctrl = get_controller()
    ctrl.restore_volume()
    click.echo("Volume restored")


@cli.command('seek')
@click.argument('position', type=float)
def seek_audio(position):
    """Seek to position in seconds"""
    ctrl = get_controller()
    ctrl.seek(position)
    click.echo(f"Seeked to {position}s")


@cli.command('chapter')
@click.argument('chapter_name', required=False)
@click.option('--next', '-n', 'next_chapter', is_flag=True,
              help='Skip to next chapter')
@click.option('--previous', '-p', 'prev_chapter', is_flag=True,
              help='Go to previous chapter')
@click.option('--list', '-l', 'list_chapters', is_flag=True,
              help='List all chapters')
def seek_chapter(chapter_name, next_chapter, prev_chapter, list_chapters):
    """Navigate chapters/cue points"""
    ctrl = get_controller()
    
    if next_chapter:
        ctrl.next_chapter()
        click.echo("Skipped to next chapter")
    elif prev_chapter:
        ctrl.previous_chapter()
        click.echo("Went to previous chapter")
    elif list_chapters:
        if ctrl.chapters:
            click.echo("Chapters:")
            for ch in ctrl.chapters:
                click.echo(f"  {ch.time:7.1f}s - {ch.title}")
        else:
            click.echo("No chapters loaded")
    elif chapter_name:
        ctrl.seek_chapter(chapter_name)
        click.echo(f"Seeked to chapter: {chapter_name}")
    else:
        click.echo("Specify a chapter name or use --next/--previous/--list")


@cli.command('status')
@click.option('--json', '-j', 'as_json', is_flag=True,
              help='Output as JSON')
@click.option('--watch', '-w', is_flag=True,
              help='Watch status continuously')
def get_status(as_json, watch):
    """Get current playback status"""
    import time
    
    ctrl = get_controller()
    
    def show_status():
        state = ctrl.get_state()
        
        if as_json:
            click.echo(json.dumps({
                'playing': state.playing,
                'position': state.position,
                'duration': state.duration,
                'volume': state.volume,
                'filename': state.filename
            }, indent=2))
        else:
            status = "Playing" if state.playing else "Paused"
            click.echo(f"Status: {status}")
            click.echo(f"Volume: {state.volume}")
            if state.filename:
                click.echo(f"File: {state.filename}")
                if state.duration > 0:
                    pct = (state.position / state.duration * 100) if state.duration else 0
                    click.echo(f"Position: {state.position:.1f}s / {state.duration:.1f}s ({pct:.1f}%)")
    
    if watch:
        try:
            while True:
                click.clear()
                show_status()
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        show_status()


@cli.command('mfp')
@click.argument('episode', type=int)
@click.option('--list', '-l', 'list_episodes', is_flag=True,
              help='List available episodes')
def music_for_programming(episode, list_episodes):
    """Play Music for Programming episode"""
    ctrl = get_controller()
    
    if list_episodes:
        click.echo("Music for Programming Episodes:")
        click.echo("  1: Datassette - Forgotten Light")
        click.echo("  2: Sunjammer - Abe Mangger")
        click.echo("  (Episodes 1-70+ available)")
        click.echo("\nUse: audio-control mfp <number> to play")
    else:
        ctrl.play_music_for_programming(episode)
        click.echo(f"Playing Music for Programming episode {episode}")


@cli.command('load-chapters')
@click.argument('chapter_file', type=click.Path(exists=True))
def load_chapters(chapter_file):
    """Load chapter markers from JSON file
    
    File format:
    {
      "chapters": [
        {"title": "Intro", "time": 0},
        {"title": "Main", "time": 120}
      ]
    }
    """
    ctrl = get_controller()
    
    with open(chapter_file, 'r') as f:
        data = json.load(f)
    
    chapters = [
        Chapter(ch['title'], ch['time'])
        for ch in data.get('chapters', [])
    ]
    
    ctrl.load_chapters(chapters)
    click.echo(f"Loaded {len(chapters)} chapters from {chapter_file}")


@cli.command('tts')
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--no-duck', is_flag=True,
              help="Don't duck background audio")
def play_tts(audio_file, no_duck):
    """Play TTS output with automatic volume ducking"""
    ctrl = get_controller()
    
    if not no_duck:
        ctrl.duck_volume()
        click.echo("Volume ducked")
    
    ctrl.play(audio_file)
    click.echo(f"Playing TTS: {audio_file}")
    
    # Note: In production, would monitor completion to restore volume


@cli.command('tool-sound')
@click.argument('tool_name')
@click.option('--list', '-l', 'list_sounds', is_flag=True,
              help='List available tool sounds')
def play_tool_sound(tool_name, list_sounds):
    """Play sound effect for tool usage"""
    sound_map = {
        'bash': 'kick',
        'grep': 'hihat',
        'read': 'snare',
        'write': 'clap',
        'edit': 'cowbell',
        'multi_edit': 'cymbal',
        'task': 'tom',
        'web_fetch': 'rimshot',
        'web_search': 'shaker',
        'converse': 'bell'
    }
    
    if list_sounds:
        click.echo("Tool Sound Mappings:")
        for tool, sound in sound_map.items():
            click.echo(f"  {tool:12} -> {sound}")
    else:
        sound = sound_map.get(tool_name, 'click')
        click.echo(f"Playing sound '{sound}' for tool '{tool_name}'")
        # In production, would play actual sound file


@cli.command('quit')
@click.option('--force', '-f', is_flag=True,
              help='Force quit without confirmation')
def quit_mpv(force):
    """Quit MPV and cleanup"""
    if not force:
        if not click.confirm("Quit MPV?"):
            return
    
    ctrl = get_controller()
    ctrl.cleanup()
    click.echo("MPV stopped and cleaned up")


# Enable shell completion
def get_completion():
    """Get shell completion script"""
    return """
# Bash completion for audio-control
_audio_control_completion() {
    local cur prev commands
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="play pause resume stop volume duck restore seek chapter status mfp load-chapters tts tool-sound quit"
    
    if [[ ${COMP_CWORD} -eq 1 ]]; then
        COMPREPLY=($(compgen -W "${commands}" -- ${cur}))
    fi
    
    case "${prev}" in
        volume)
            COMPREPLY=($(compgen -W "0 25 50 75 100" -- ${cur}))
            ;;
        mfp)
            COMPREPLY=($(compgen -W "1 2 3 4 5 6 7 8 9 10" -- ${cur}))
            ;;
        tool-sound)
            COMPREPLY=($(compgen -W "bash grep read write edit task" -- ${cur}))
            ;;
    esac
}

complete -F _audio_control_completion audio-control
"""


@cli.command('completion')
@click.option('--shell', type=click.Choice(['bash', 'zsh', 'fish']),
              default='bash', help='Shell type')
def show_completion(shell):
    """Show shell completion script
    
    To enable completion, add this to your shell config:
    
    eval "$(audio-control completion)"
    """
    if shell == 'bash':
        click.echo(get_completion())
    else:
        click.echo(f"# Completion for {shell} not yet implemented")
        click.echo("# Contributions welcome!")


def main():
    """Main entry point"""
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        # Cleanup on exit
        if controller:
            controller.cleanup()


if __name__ == '__main__':
    main()