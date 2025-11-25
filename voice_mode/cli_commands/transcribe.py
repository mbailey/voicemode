"""CLI command for audio transcription."""

import click
import json
import asyncio
from pathlib import Path
from typing import Optional


@click.group()
def transcribe():
    """Audio transcription with word-level timestamps."""
    pass


@transcribe.command("audio")
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--words', is_flag=True, help='Include word-level timestamps')
@click.option(
    '--backend',
    type=click.Choice(['openai', 'whisperx', 'whisper-cpp', 'whisper-cli']),
    default='openai',
    help='Transcription backend to use'
)
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'srt', 'vtt', 'csv']),
    default='json',
    help='Output format for transcription'
)
@click.option('--output', '-o', type=click.Path(), help='Save transcription to file')
@click.option('--language', help='Language code (e.g., en, es, fr)')
@click.option('--model', default='whisper-1', help='Model to use (for OpenAI backend)')
def audio_command(
    audio_file: str,
    words: bool,
    backend: str,
    output_format: str,
    output: Optional[str],
    language: Optional[str],
    model: str
):
    """
    Transcribe audio with optional word-level timestamps.
    
    Examples:
    
        voice-mode transcribe audio recording.mp3
        
        voice-mode transcribe audio interview.wav --words
        
        voice-mode transcribe audio podcast.mp3 --words --format srt -o subtitles.srt
        
        voice-mode transcribe audio spanish.mp3 --language es --backend whisperx
    """
    async def run():
        # Import here to avoid loading tools at module level
        from voice_mode.tools.transcription import (
            transcribe_audio,
            TranscriptionBackend,
            OutputFormat
        )

        # Perform transcription
        result = await transcribe_audio(
            audio_file=audio_file,
            word_timestamps=words,
            backend=TranscriptionBackend(backend),
            output_format=OutputFormat(output_format),
            language=language,
            model=model
        )
        
        # Check for errors
        if not result.get("success", False):
            error_msg = result.get("error", "Unknown error occurred")
            click.echo(f"Error: {error_msg}", err=True)
            return
        
        # Format output
        if output_format == 'json':
            # Remove internal fields for cleaner output
            output_result = {k: v for k, v in result.items() 
                           if k not in ['formatted_content']}
            content = json.dumps(output_result, indent=2)
        elif "formatted_content" in result:
            content = result["formatted_content"]
        else:
            # Fallback to JSON if format conversion failed
            content = json.dumps(result, indent=2)
        
        # Write output
        if output:
            Path(output).write_text(content)
            click.echo(f"Transcription saved to {output}")
        else:
            click.echo(content)
    
    # Run async function
    asyncio.run(run())


# For backward compatibility, also provide a direct command
@click.command('transcribe-audio')
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--words', is_flag=True, help='Include word-level timestamps')
@click.option(
    '--backend',
    type=click.Choice(['openai', 'whisperx', 'whisper-cpp', 'whisper-cli']),
    default='openai',
    help='Transcription backend'
)
@click.option(
    '--format',
    'output_format',
    type=click.Choice(['json', 'srt', 'vtt', 'csv']),
    default='json',
    help='Output format'
)
@click.option('--output', '-o', type=click.Path(), help='Save to file')
@click.option('--language', help='Language code')
@click.option('--model', default='whisper-1', help='Model to use')
def transcribe_audio_command(
    audio_file: str,
    words: bool,
    backend: str,
    output_format: str,
    output: Optional[str],
    language: Optional[str],
    model: str
):
    """Direct transcription command for backward compatibility."""
    audio_command.callback(
        audio_file=audio_file,
        words=words,
        backend=backend,
        output_format=output_format,
        output=output,
        language=language,
        model=model
    )