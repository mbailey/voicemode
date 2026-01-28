# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "pandas",
#     "scipy",
#     "matplotlib",
#     "numpy",
#     "anywidget",
#     "traitlets",
# ]
# ///
"""
MFP CUE Editor - Marimo app for editing chapter timestamps.

This module provides a visual waveform editor for adjusting Music For Programming
episode chapter timestamps. It's designed to be run via `voicemode dj mfp edit`.

The editor:
- Displays an interactive waveform using WaveSurfer.js
- Shows draggable region markers for each chapter
- Auto-saves changes to the CUE file
- Persists unsaved edits in localStorage

Usage:
    voicemode dj mfp edit           # Edit first available episode
    voicemode dj mfp edit 49        # Edit episode 49
"""

import marimo

__generated_with = "0.18.4"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    # State for triggering refresh after save
    get_refresh, set_refresh = mo.state(0)
    return get_refresh, set_refresh


@app.cell
def _(mo):
    mo.md(r"""
    # MFP CUE Editor

    Edit chapter timestamps for Music For Programming episodes.
    """)
    return


@app.cell
def _():
    from pathlib import Path
    import re
    return Path, re


@app.cell
def _(Path):
    # MFP directory and config - standardized location for VoiceMode
    MFP_DIR = Path.home() / ".voicemode" / "music-for-programming"
    FAVORITES_FILE = MFP_DIR / "favorites.json"
    return MFP_DIR, FAVORITES_FILE


@app.cell
def _(FAVORITES_FILE, MFP_DIR, Path):
    import json as json_lib
    import re as re_lib

    # MFP RSS base URL for streaming
    MFP_BASE_URL = "https://datashat.net/music_for_programming_"

    def load_favorites():
        """Load favorites list from config file."""
        if FAVORITES_FILE.exists():
            try:
                data = json_lib.loads(FAVORITES_FILE.read_text())
                return set(data.get("favorites", []))
            except:
                return set()
        return set()

    def get_streaming_url(cue_name: str) -> str | None:
        """Extract streaming URL from CUE filename.

        CUE files are named like: music_for_programming_49-julien_mier.cue
        Streaming URL: https://datashat.net/music_for_programming_49-julien_mier.mp3
        """
        if cue_name.startswith("music_for_programming_"):
            return f"{MFP_BASE_URL}{cue_name[len('music_for_programming_'):]}.mp3"
        return None

    def get_episodes():
        """Scan MFP directory for CUE and CUE-draft files (that's what we edit).

        Files with .cue extension are complete (all tracks have timestamps).
        Files with .cue-draft extension are incomplete (tracks without timestamps).
        """
        episodes = []
        seen_names = set()

        # Find all .cue and .cue-draft files in the directory
        for pattern in ["*.cue", "*.cue-draft"]:
            for cue_file in sorted(MFP_DIR.glob(pattern)):
                # Handle both .cue and .cue-draft extensions
                if cue_file.suffix == ".cue-draft":
                    name = cue_file.name[:-10]  # Remove .cue-draft
                    is_draft = True
                else:
                    name = cue_file.stem  # Remove .cue
                    is_draft = False

                # Skip if we've already processed this episode (prefer .cue over .cue-draft)
                if name in seen_names:
                    continue
                seen_names.add(name)

                # Check completion status
                cue_content = cue_file.read_text()
                track_count = cue_content.count("TRACK ")
                index_count = cue_content.count("INDEX 01")
                is_completed = track_count > 0 and track_count == index_count

                # Look for matching MP3 (same basename)
                mp3_file = MFP_DIR / f"{name}.mp3"
                has_audio = mp3_file.exists()

                # Get streaming URL for fallback
                streaming_url = get_streaming_url(name)

                episodes.append({
                    "name": name,
                    "path": str(cue_file),  # Path to CUE or CUE-draft file
                    "mp3_path": str(mp3_file) if has_audio else None,
                    "streaming_url": streaming_url,
                    "completed": is_completed,
                    "is_draft": is_draft,
                    "has_audio": has_audio,
                })

        return episodes

    all_episodes = get_episodes()
    favorites_set = load_favorites()

    # Add favorite flag to episodes
    for _ep in all_episodes:
        _ep["favorite"] = _ep["name"] in favorites_set

    return MFP_BASE_URL, all_episodes, favorites_set, get_episodes, get_streaming_url, json_lib, load_favorites, re_lib


@app.cell
def _(Path, re):
    def parse_cue_file(cue_path: Path) -> dict:
        """Parse a CUE file and return structured data."""
        content = cue_path.read_text()

        # Extract header info
        header = {}
        title_match = re.search(r'^TITLE "(.+)"', content, re.MULTILINE)
        performer_match = re.search(r'^PERFORMER "(.+)"', content, re.MULTILINE)
        file_match = re.search(r'^FILE "(.+)"', content, re.MULTILINE)

        if title_match:
            header['title'] = title_match.group(1)
        if performer_match:
            header['performer'] = performer_match.group(1)
        if file_match:
            header['file'] = file_match.group(1)

        # Extract tracks - handle both with and without INDEX timestamps
        tracks = []

        # Pattern for tracks WITH timestamps
        track_with_index_pattern = re.compile(
            r'TRACK (\d+) AUDIO\s+'
            r'TITLE "(.+?)"\s+'
            r'PERFORMER "(.+?)"\s+'
            r'(?:REM[^\n]*\s+)*'  # Optional REM lines
            r'INDEX 01 (\d+):(\d+):(\d+)',
            re.MULTILINE | re.DOTALL
        )

        # Pattern for tracks WITHOUT timestamps (just TRACK, TITLE, PERFORMER)
        track_without_index_pattern = re.compile(
            r'TRACK (\d+) AUDIO\s+'
            r'TITLE "(.+?)"\s+'
            r'PERFORMER "(.+?)"',
            re.MULTILINE | re.DOTALL
        )

        # First, find all tracks (with or without timestamps)
        all_tracks = {}
        for match in track_without_index_pattern.finditer(content):
            track_num = int(match.group(1))
            title = match.group(2)
            performer = match.group(3)
            all_tracks[track_num] = {
                'track': track_num,
                'performer': performer,
                'title': title,
                'start': '--:--',
                'start_seconds': 0,
                'has_timestamp': False
            }

        # Then, update with timestamps for those that have them
        for match in track_with_index_pattern.finditer(content):
            track_num = int(match.group(1))
            title = match.group(2)
            performer = match.group(3)
            minutes = int(match.group(4))
            seconds = int(match.group(5))
            frames = int(match.group(6))

            # Convert to total seconds (75 frames per second in CUE format)
            total_seconds = minutes * 60 + seconds + frames / 75

            # Format as MM:SS
            mm = int(total_seconds // 60)
            ss = int(total_seconds % 60)
            time_str = f"{mm:02d}:{ss:02d}"

            all_tracks[track_num] = {
                'track': track_num,
                'performer': performer,
                'title': title,
                'start': time_str,
                'start_seconds': total_seconds,
                'has_timestamp': True
            }

        # Convert to sorted list
        tracks = [all_tracks[k] for k in sorted(all_tracks.keys())]

        return {'header': header, 'tracks': tracks}

    def get_reference_files(sidecar_path):
        """Find reference track files in the references subfolder."""
        refs_dir = sidecar_path / "references" if sidecar_path else None
        refs = {}
        if refs_dir and refs_dir.exists():
            # Reference files are named like: 01_artist_title.wav or 01_artist_title.mp3
            for f in refs_dir.glob("*"):
                if f.suffix.lower() in ('.wav', '.mp3', '.flac') and not f.name.endswith('.asd'):
                    # Extract track number from filename (first part before underscore)
                    parts = f.name.split('_', 1)
                    if parts[0].isdigit():
                        track_num = int(parts[0])
                        refs[track_num] = str(f)
        return refs

    return get_reference_files, parse_cue_file


@app.cell
def _(MFP_DIR, json_lib, mo):
    # Load saved filter settings
    SETTINGS_FILE = MFP_DIR / "editor_settings.json"

    def load_settings():
        if SETTINGS_FILE.exists():
            try:
                return json_lib.loads(SETTINGS_FILE.read_text())
            except:
                pass
        return {"favorites_only": True, "completed_only": False, "has_audio": True}

    saved_settings = load_settings()

    # Filter checkboxes with saved defaults
    show_favorites_only = mo.ui.checkbox(label="Favorites only", value=saved_settings.get("favorites_only", True))
    show_completed_only = mo.ui.checkbox(label="Completed only", value=saved_settings.get("completed_only", False))
    show_with_audio_only = mo.ui.checkbox(label="Has audio", value=saved_settings.get("has_audio", True))
    return SETTINGS_FILE, load_settings, saved_settings, show_completed_only, show_favorites_only, show_with_audio_only


@app.cell
def _(SETTINGS_FILE, json_lib, show_completed_only, show_favorites_only, show_with_audio_only):
    # Auto-save filter settings when they change
    current_settings = {
        "favorites_only": show_favorites_only.value,
        "completed_only": show_completed_only.value,
        "has_audio": show_with_audio_only.value,
    }
    SETTINGS_FILE.write_text(json_lib.dumps(current_settings, indent=2))
    return (current_settings,)


@app.cell
def _(all_episodes, mo, show_completed_only, show_favorites_only, show_with_audio_only):
    # Filter episodes based on checkboxes
    filtered_episodes = all_episodes.copy()

    if show_favorites_only.value:
        filtered_episodes = [ep for ep in filtered_episodes if ep["favorite"]]
    if show_completed_only.value:
        filtered_episodes = [ep for ep in filtered_episodes if ep["completed"]]
    if show_with_audio_only.value:
        filtered_episodes = [ep for ep in filtered_episodes if ep["has_audio"]]

    # Build dropdown options: "49: Julien Mier" -> path
    # Status indicators: ★ = favorite, ✓ = complete, 📝 = draft
    episode_options = {}
    for _ep in filtered_episodes:
        # Parse episode number and artist from name like "music_for_programming_49-julien_mier"
        _name = _ep["name"]
        if _name.startswith("music_for_programming_"):
            _rest = _name[len("music_for_programming_"):]
            _parts = _rest.split("-", 1)
            _num = _parts[0]
            _artist = _parts[1].replace("_", " ") if len(_parts) > 1 else "Unknown"
        else:
            _num = "?"
            _artist = _name
        # Add indicators for status
        _status = ""
        if _ep["favorite"]:
            _status += "★ "
        if _ep.get("is_draft"):
            _status += "📝 "  # Draft indicator
        elif _ep["completed"]:
            _status += "✓ "
        _label = f"{_status}{_num}: {_artist}"
        episode_options[_label] = _ep["path"]

    # Create dropdown (default to first favorite, or first episode)
    default_ep = None
    for _ep in filtered_episodes:
        if _ep["favorite"]:
            _name = _ep["name"]
            if _name.startswith("music_for_programming_"):
                _rest = _name[len("music_for_programming_"):]
                _parts = _rest.split("-", 1)
                _num = _parts[0]
                _artist = _parts[1].replace("_", " ") if len(_parts) > 1 else "Unknown"
            else:
                _num = "?"
                _artist = _name
            _status = "★ " + ("📝 " if _ep.get("is_draft") else ("✓ " if _ep["completed"] else ""))
            default_ep = f"{_status}{_num}: {_artist}"
            break

    if not default_ep and episode_options:
        default_ep = list(episode_options.keys())[0]

    episode_dropdown = mo.ui.dropdown(
        options=episode_options,
        label="Episode",
        value=default_ep
    ) if episode_options else mo.md("**No episodes match filters**")

    return default_ep, episode_dropdown, episode_options, filtered_episodes


@app.cell
def _(Path, episode_dropdown):
    # Get selected sidecar path from dropdown
    if hasattr(episode_dropdown, 'value') and episode_dropdown.value:
        sidecar_path_value = episode_dropdown.value
    else:
        sidecar_path_value = None
    return (sidecar_path_value,)


@app.cell
def _(Path, all_episodes, episode_dropdown, sidecar_path_value):
    # Get selected CUE file path and find matching MP3 or streaming URL
    # sidecar_path_value is now a CUE file path (or None)
    cue_path = Path(sidecar_path_value) if sidecar_path_value else None
    mp3_path = None
    streaming_url = None
    mfp_dir = None
    is_draft = False  # Track if this is a .cue-draft file
    episode_name = None  # Base name for graduation

    if cue_path and cue_path.exists():
        mfp_dir = cue_path.parent  # Directory containing the files
        is_draft = cue_path.name.endswith(".cue-draft")

        # Get base name (without .cue or .cue-draft extension)
        if is_draft:
            episode_name = cue_path.name[:-10]  # Remove .cue-draft
        else:
            episode_name = cue_path.stem

        # Find matching MP3 and streaming URL from episode data
        for ep in all_episodes:
            if ep["path"] == str(cue_path):
                if ep.get("mp3_path"):
                    mp3_path = Path(ep["mp3_path"])
                streaming_url = ep.get("streaming_url")
                break
        # Fallback: check for MP3 with same basename
        if not mp3_path:
            mp3_file = mfp_dir / f"{episode_name}.mp3"
            if mp3_file.exists():
                mp3_path = mp3_file

    return cue_path, episode_name, is_draft, mfp_dir, mp3_path, streaming_url


@app.cell
def _(all_episodes, episode_dropdown, mo, show_completed_only, show_favorites_only, show_with_audio_only):
    # Display the controls with filters
    filter_row = mo.hstack([
        show_favorites_only,
        show_completed_only,
        show_with_audio_only,
        mo.md(f"*{len(all_episodes)} CUE files total*")
    ], gap=2)

    controls = mo.vstack([
        filter_row,
        episode_dropdown if hasattr(episode_dropdown, 'value') else episode_dropdown,
    ])
    controls
    return controls, filter_row


@app.cell
def _(cue_path, get_refresh, parse_cue_file):
    # Parse the selected CUE file (re-parses when get_refresh changes)
    _ = get_refresh()  # Dependency to trigger re-parse after save
    if cue_path and cue_path.exists():
        cue_data = parse_cue_file(cue_path)
    else:
        cue_data = None
    return (cue_data,)


@app.cell
def _(cue_data, is_draft, mo):
    # Display header info
    if cue_data:
        _hdr = cue_data['header']
        _draft_badge = "📝 **DRAFT** - " if is_draft else ""
        header_display = mo.md(f"""
## {_hdr.get('title', 'Unknown')}

{_draft_badge}**Performer:** {_hdr.get('performer', 'Unknown')}
**Audio File:** `{_hdr.get('file', 'Unknown')}`
        """)
    else:
        header_display = mo.md("*Select a CUE file to view*")

    header_display
    return (header_display,)


@app.cell
def _():
    import numpy as np
    from scipy.io import wavfile
    import matplotlib.pyplot as plt
    import threading
    import http.server
    import socketserver
    return np, plt, wavfile, threading, http, socketserver


@app.cell
def _(MFP_DIR, Path, threading, http, socketserver):
    import json as json_module
    # Start HTTP server to serve audio files AND handle timestamp updates
    # Serve from MFP_DIR so all episodes are accessible
    AUDIO_SERVER_PORT = 8082

    # Use factory function to capture MFP_DIR in closure
    def make_audio_handler(mfp_dir, json_mod):
        class AudioHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(mfp_dir), **kwargs)

            def log_message(self, format, *args):
                pass  # Suppress logging

            def do_POST(self):
                """Handle POST requests for timestamp updates."""
                if self.path == '/update-timestamps':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    try:
                        data = json_mod.loads(post_data)
                        cue_file = data.get('cue_file')  # e.g., "018_Episode.mp3.d/tracks.cue"
                        updates = data.get('updates', {})  # {track_num: new_start_seconds}

                        if cue_file and updates:
                            # cue_file now includes the sidecar subdir path
                            cue_path = mfp_dir / cue_file
                            if cue_path.exists():
                                self._update_cue_file(cue_path, updates)
                                self.send_response(200)
                                self.send_header('Content-Type', 'application/json')
                                self.send_header('Access-Control-Allow-Origin', '*')
                                self.end_headers()
                                self.wfile.write(b'{"status": "ok"}')
                                return

                        self.send_response(400)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(b'{"error": "Invalid request"}')
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(f'{{"error": "{str(e)}"}}'.encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_OPTIONS(self):
                """Handle CORS preflight."""
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()

            def _update_cue_file(self, cue_path, updates):
                """Update CUE file with new timestamps, including adding INDEX lines to existing tracks."""
                import re as re_mod
                content = cue_path.read_text()
                lines = content.split('\n')
                new_lines = []
                current_track = None
                existing_tracks = set()
                tracks_with_index = set()

                # First pass: identify existing tracks and which have INDEX lines
                for i, line in enumerate(lines):
                    track_match = re_mod.match(r'\s*TRACK (\d+) AUDIO', line)
                    if track_match:
                        current_track = int(track_match.group(1))
                        existing_tracks.add(current_track)

                    index_match = re_mod.match(r'\s*INDEX 01', line)
                    if index_match and current_track:
                        tracks_with_index.add(current_track)

                # Second pass: update or add INDEX lines
                current_track = None
                i = 0
                while i < len(lines):
                    line = lines[i]

                    track_match = re_mod.match(r'\s*TRACK (\d+) AUDIO', line)
                    if track_match:
                        current_track = int(track_match.group(1))

                    index_match = re_mod.match(r'(\s*)INDEX 01 (\d+):(\d+):(\d+)', line)
                    if index_match and current_track and str(current_track) in updates:
                        # Update existing INDEX line
                        indent = index_match.group(1)
                        new_seconds = float(updates[str(current_track)])
                        mins = int(new_seconds // 60)
                        secs = int(new_seconds % 60)
                        frames = int((new_seconds % 1) * 75)
                        new_lines.append(f'{indent}INDEX 01 {mins:02d}:{secs:02d}:{frames:02d}')
                        i += 1
                        continue

                    # Check if we need to add INDEX line before next TRACK or end of file
                    next_track_match = None
                    if i + 1 < len(lines):
                        next_track_match = re_mod.match(r'\s*TRACK (\d+) AUDIO', lines[i + 1])

                    # If current track needs INDEX and doesn't have one, add it after PERFORMER line
                    if current_track and str(current_track) in updates and current_track not in tracks_with_index:
                        # Check if this is a PERFORMER line or next line is a TRACK/end
                        is_performer = re_mod.match(r'\s*PERFORMER', line)
                        if is_performer or next_track_match or i == len(lines) - 1:
                            new_lines.append(line)
                            # Add INDEX line after PERFORMER
                            if is_performer:
                                new_seconds = float(updates[str(current_track)])
                                mins = int(new_seconds // 60)
                                secs = int(new_seconds % 60)
                                frames = int((new_seconds % 1) * 75)
                                new_lines.append(f'    INDEX 01 {mins:02d}:{secs:02d}:{frames:02d}')
                                tracks_with_index.add(current_track)  # Mark as done
                            i += 1
                            continue

                    new_lines.append(line)
                    i += 1

                # Find completely new tracks that need to be added
                new_track_nums = []
                for track_str in updates.keys():
                    track_num = int(track_str)
                    if track_num not in existing_tracks:
                        new_track_nums.append(track_num)

                # Add new tracks at the end (sorted by timestamp)
                if new_track_nums:
                    new_track_nums.sort(key=lambda t: float(updates[str(t)]))

                    # Get performer from header
                    performer = "Unknown"
                    for line in lines:
                        perf_match = re_mod.match(r'^PERFORMER "(.+)"', line)
                        if perf_match:
                            performer = perf_match.group(1)
                            break

                    # Remove trailing empty lines
                    while new_lines and new_lines[-1].strip() == '':
                        new_lines.pop()

                    for track_num in new_track_nums:
                        new_seconds = float(updates[str(track_num)])
                        mins = int(new_seconds // 60)
                        secs = int(new_seconds % 60)
                        frames = int((new_seconds % 1) * 75)

                        new_lines.append(f'  TRACK {track_num:02d} AUDIO')
                        new_lines.append(f'    TITLE "Track {track_num}"')
                        new_lines.append(f'    PERFORMER "{performer}"')
                        new_lines.append(f'    INDEX 01 {mins:02d}:{secs:02d}:{frames:02d}')

                cue_path.write_text('\n'.join(new_lines))

        return AudioHandler

    # Create handler class with MFP_DIR captured
    AudioHandler = make_audio_handler(MFP_DIR, json_module)

    def start_audio_server():
        try:
            with socketserver.TCPServer(("", AUDIO_SERVER_PORT), AudioHandler) as httpd:
                httpd.serve_forever()
        except OSError:
            pass  # Port already in use, that's fine

    # Start server in background thread (only if not already running)
    server_thread = threading.Thread(target=start_audio_server, daemon=True)
    server_thread.start()

    return AUDIO_SERVER_PORT, AudioHandler, server_thread, start_audio_server


@app.cell
def _():
    import subprocess
    import shutil
    return subprocess, shutil


@app.cell
def _(MFP_DIR, Path, episode_name, mo, mp3_path, streaming_url, subprocess, shutil):
    # Find audio file for waveform display
    # Prefer local MP3, fall back to streaming URL
    preview_status = None
    wav_path = None
    wav_filename = None
    audio_url = None  # URL for WaveSurfer (local or streaming)
    download_button = None  # Button to download MP3 when streaming
    download_target = None  # Target path for download

    if mp3_path and mp3_path.exists():
        # Use the local MP3 directly
        wav_path = mp3_path
        wav_filename = mp3_path.name
        file_size_mb = mp3_path.stat().st_size / (1024 * 1024)
        preview_status = mo.md(f"*Audio: {mp3_path.name} ({file_size_mb:.0f} MB) - local*")
    elif streaming_url:
        # Fall back to streaming URL, offer download
        audio_url = streaming_url
        # Calculate target path for download
        if episode_name:
            download_target = MFP_DIR / f"{episode_name}.mp3"
        download_button = mo.ui.run_button(label="⬇️ Download MP3", kind="neutral")
        preview_status = mo.hstack([
            mo.md(f"*Audio: Streaming from datashat.net*"),
            download_button
        ], gap=2)
    elif mp3_path:
        preview_status = mo.callout(
            mo.md(f"**MP3 not found:** `{mp3_path.name}` and no streaming URL available"),
            kind="warn"
        )
    else:
        preview_status = mo.callout(
            mo.md("**Select an episode to view audio**"),
            kind="info"
        )

    return audio_url, download_button, download_target, preview_status, wav_filename, wav_path


@app.cell
def _(download_button, download_target, get_refresh, mo, set_refresh, streaming_url):
    # Handle download button click
    download_status = None

    if download_button is not None and download_button.value and streaming_url and download_target:
        import urllib.request
        import urllib.error

        try:
            # Show downloading status
            download_status = mo.callout(
                mo.md(f"**Downloading...** `{download_target.name}`"),
                kind="info"
            )

            # Download the file
            urllib.request.urlretrieve(streaming_url, download_target)

            # Get file size
            _file_size_mb = download_target.stat().st_size / (1024 * 1024)

            # Trigger refresh to update the audio source
            set_refresh(get_refresh() + 1)

            download_status = mo.callout(
                mo.md(f"✅ **Downloaded!** `{download_target.name}` ({_file_size_mb:.0f} MB)\n\nRefresh the page to use the local file."),
                kind="success"
            )
        except urllib.error.URLError as e:
            download_status = mo.callout(
                mo.md(f"**Download failed:** {e.reason}"),
                kind="danger"
            )
        except Exception as e:
            download_status = mo.callout(
                mo.md(f"**Download failed:** {e}"),
                kind="danger"
            )

    download_status
    return (download_status,)


@app.cell
def _(AUDIO_SERVER_PORT, MFP_DIR, audio_url, cue_data, cue_path, get_refresh, mo, wav_filename):
    # Create WaveSurfer widget - write HTML to MFP_DIR and load via iframe
    refresh_count = get_refresh()  # Cache-bust when CUE changes
    # CUE filename for save requests (relative to MFP_DIR)
    cue_relative_path = cue_path.name if cue_path else ""

    # Determine audio source: local file served via HTTP or direct streaming URL
    if wav_filename:
        audio_source = wav_filename  # Will be loaded relative to the iframe's origin
        is_streaming = False
    elif audio_url:
        audio_source = audio_url  # Direct URL to streaming source
        is_streaming = True
    else:
        audio_source = None
        is_streaming = False

    if audio_source:
        # Build regions JavaScript array (each track is a region from start to next track)
        # Only include tracks that have timestamps
        if cue_data and cue_data['tracks']:
            _tracks = [t for t in cue_data['tracks'] if t.get('has_timestamp', True)]
            _regions_list = []
            _colors = ['rgba(99, 102, 241, 0.35)', 'rgba(168, 85, 247, 0.35)']  # Alternating colors (higher opacity)
            for _i, _trk in enumerate(_tracks):
                _start = _trk['start_seconds']
                # End is next track start, or we'll set it to duration in JS
                if _i < len(_tracks) - 1:
                    _end = _tracks[_i + 1]['start_seconds']
                else:
                    _end = -1  # Placeholder, will be set to duration in JS
                _color = _colors[_i % 2]
                _regions_list.append(
                    f'{{id: "track{_trk["track"]}", start: {_start}, end: {_end}, '
                    f'content: "T{_trk["track"]}", color: "{_color}"}}'
                )
            regions_js = ",".join(_regions_list)
        else:
            regions_js = ""

        wavesurfer_html = f'''<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ margin: 0; padding: 20px; background: #1a1a2e; font-family: system-ui; }}
        #waveform {{ width: 100%; height: 128px; }}
        .controls {{ margin-top: 10px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
        button {{ padding: 8px 16px; background: #6366f1; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        button:hover {{ background: #5558dd; }}
        button.save {{ background: #22c55e; }}
        button.save:hover {{ background: #16a34a; }}
        button.save:disabled {{ background: #4b5563; cursor: not-allowed; }}
        button.add-marker {{ background: #f59e0b; }}
        button.add-marker:hover {{ background: #d97706; }}
        button.add-marker.active {{ background: #dc2626; }}
        .time {{ color: white; font-family: monospace; font-size: 16px; }}
        .time-divider {{ color: #666; }}
        .duration {{ color: #999; font-family: monospace; }}
        input[type=range] {{ width: 100px; }}
        .vol-label {{ color: #999; font-size: 12px; }}
        .track-label {{ color: white; font-size: 11px; font-weight: bold; padding: 2px 4px; }}
        .status {{ color: #fbbf24; font-size: 12px; margin-left: auto; }}
        .status.saved {{ color: #22c55e; }}
        /* Style region labels and handles */
        [data-region-id] {{ border-left: 2px solid rgba(255,255,255,0.8) !important; }}
        [data-region-id] > div {{ color: white !important; font-size: 12px; font-weight: bold; text-shadow: 0 0 3px black; }}
        /* Hide right resize handle - we only drag left edge (track start) */
        [data-resize="right"] {{ display: none !important; }}
    </style>
</head>
<body>
    <div id="waveform"></div>
    <div class="controls">
        <button id="playPause">Play</button>
        <button id="back15">-15s</button>
        <button id="back5">-5s</button>
        <button id="fwd5">+5s</button>
        <span id="currentTime" class="time">00:00</span>
        <span class="time-divider">/</span>
        <span id="duration" class="duration">Loading...</span>
        <input type="range" id="volume" min="0" max="100" value="50">
        <span class="vol-label">Vol</span>
        <button id="addMarkerBtn" class="add-marker">+ Add Marker</button>
        <button id="saveBtn" class="save" disabled>Save Changes</button>
        <span id="status" class="status"></span>
    </div>
    <script type="module">
        import WaveSurfer from 'https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js';
        import RegionsPlugin from 'https://unpkg.com/wavesurfer.js@7/dist/plugins/regions.esm.js';

        const regions = RegionsPlugin.create();
        const pendingChanges = {{}};  // Track changes: {{trackNum: newStartSeconds}}
        const originalStarts = {{}};  // Track original start times for comparison
        const CUE_FILE = '{cue_relative_path}';
        const STORAGE_KEY = 'mfp-cue-editor-' + CUE_FILE;

        // localStorage helpers
        function saveToStorage() {{
            if (Object.keys(pendingChanges).length > 0) {{
                localStorage.setItem(STORAGE_KEY, JSON.stringify(pendingChanges));
            }} else {{
                localStorage.removeItem(STORAGE_KEY);
            }}
        }}

        function loadFromStorage() {{
            try {{
                const saved = localStorage.getItem(STORAGE_KEY);
                return saved ? JSON.parse(saved) : {{}};
            }} catch (e) {{
                return {{}};
            }}
        }}

        function clearStorage() {{
            localStorage.removeItem(STORAGE_KEY);
        }}

        const wavesurfer = WaveSurfer.create({{
            container: '#waveform',
            waveColor: '#6366f1',
            progressColor: '#a855f7',
            cursorColor: '#fff',
            cursorWidth: 2,
            barWidth: 2,
            barGap: 1,
            height: 128,
            normalize: true,
            plugins: [regions],
        }});

        // Load audio from same origin (file in MFP_DIR)
        // Load audio - either local file served via HTTP or direct streaming URL
        wavesurfer.load('{audio_source}');

        const playPauseBtn = document.getElementById('playPause');
        const back15Btn = document.getElementById('back15');
        const back5Btn = document.getElementById('back5');
        const fwd5Btn = document.getElementById('fwd5');
        const currentTimeEl = document.getElementById('currentTime');
        const durationEl = document.getElementById('duration');
        const volumeSlider = document.getElementById('volume');
        const addMarkerBtn = document.getElementById('addMarkerBtn');
        const saveBtn = document.getElementById('saveBtn');
        const statusEl = document.getElementById('status');

        // Track next marker number for new markers
        let nextMarkerNum = 1;
        let addMarkerMode = false;
        let disableDragSelection = null;

        function formatTime(seconds) {{
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
        }}

        function updateSaveButton() {{
            const changeCount = Object.keys(pendingChanges).length;
            if (changeCount > 0) {{
                saveBtn.disabled = false;
                saveBtn.textContent = `Save Changes (${{changeCount}})`;
                statusEl.textContent = `${{changeCount}} unsaved change(s)`;
                statusEl.className = 'status';
            }} else {{
                saveBtn.disabled = true;
                saveBtn.textContent = 'Save Changes';
                statusEl.textContent = '';
            }}
        }}

        wavesurfer.on('ready', () => {{
            const duration = wavesurfer.getDuration();
            durationEl.textContent = formatTime(duration);
            wavesurfer.setVolume(0.5);

            // Add track regions (draggable by left edge)
            const trackRegions = [{regions_js}];
            trackRegions.forEach((r, idx) => {{
                const end = r.end < 0 ? duration : r.end;
                const trackNum = parseInt(r.id.replace('track', ''));
                originalStarts[trackNum] = r.start;  // Store original start
                regions.addRegion({{
                    id: r.id,
                    start: r.start,
                    end: end,
                    color: r.color,
                    content: r.content,
                    drag: false,          // Don't allow dragging whole region
                    resize: true,         // Allow resizing (left edge) for all tracks
                }});
            }});

            // Restore any saved changes from localStorage
            const savedChanges = loadFromStorage();
            if (Object.keys(savedChanges).length > 0) {{
                // Apply saved changes to regions
                for (const [trackNumStr, newStart] of Object.entries(savedChanges)) {{
                    const trackNum = parseInt(trackNumStr);
                    const region = regions.getRegions().find(r => r.id === 'track' + trackNum);
                    if (region) {{
                        region.setOptions({{ start: newStart }});
                        originalStarts[trackNum] = newStart;
                        pendingChanges[trackNum] = newStart;

                        // Update previous track's end to match
                        if (trackNum > 1) {{
                            const prevRegion = regions.getRegions().find(r => r.id === 'track' + (trackNum - 1));
                            if (prevRegion) {{
                                prevRegion.setOptions({{ end: newStart }});
                            }}
                        }}
                    }}
                }}
                updateSaveButton();
                statusEl.textContent = 'Restored unsaved changes from browser storage';
                statusEl.className = 'status';
            }}
        }});

        // Store expected end times (derived from next track's start)
        const expectedEnds = {{}};

        // Track region boundary changes
        regions.on('region-updated', (region) => {{
            // Extract track number from region id (e.g., "track2" -> 2)
            const trackNum = parseInt(region.id.replace('track', ''));
            const origStart = originalStarts[trackNum];
            const newStart = region.start;

            // Check if this was a left-edge (start) drag vs right-edge (end) drag
            const startChanged = Math.abs(newStart - origStart) > 0.1;

            if (startChanged) {{
                // Left edge dragged - this is what we want
                // Store the change
                pendingChanges[trackNum] = newStart;
                originalStarts[trackNum] = newStart;  // Update for next comparison
                updateSaveButton();
                saveToStorage();  // Persist to localStorage

                // Update the previous track's end to match (no gaps)
                if (trackNum > 1) {{
                    const prevTrackId = 'track' + (trackNum - 1);
                    const prevRegion = regions.getRegions().find(r => r.id === prevTrackId);
                    if (prevRegion) {{
                        prevRegion.setOptions({{ end: newStart }});
                    }}
                }}
            }} else {{
                // Right edge dragged - revert it by setting end to next track's start
                const nextTrackId = 'track' + (trackNum + 1);
                const nextRegion = regions.getRegions().find(r => r.id === nextTrackId);
                if (nextRegion) {{
                    region.setOptions({{ end: nextRegion.start }});
                }} else {{
                    // Last track - set to duration
                    region.setOptions({{ end: wavesurfer.getDuration() }});
                }}
            }}
        }});

        // Click on region to seek to its start
        regions.on('region-clicked', (region, e) => {{
            e.stopPropagation();
            region.play();
        }});

        wavesurfer.on('audioprocess', () => {{
            currentTimeEl.textContent = formatTime(wavesurfer.getCurrentTime());
        }});

        wavesurfer.on('seeking', () => {{
            currentTimeEl.textContent = formatTime(wavesurfer.getCurrentTime());
        }});

        playPauseBtn.addEventListener('click', () => {{
            wavesurfer.playPause();
        }});

        back15Btn.addEventListener('click', () => {{
            const newTime = Math.max(0, wavesurfer.getCurrentTime() - 15);
            wavesurfer.seekTo(newTime / wavesurfer.getDuration());
        }});

        back5Btn.addEventListener('click', () => {{
            const newTime = Math.max(0, wavesurfer.getCurrentTime() - 5);
            wavesurfer.seekTo(newTime / wavesurfer.getDuration());
        }});

        fwd5Btn.addEventListener('click', () => {{
            const duration = wavesurfer.getDuration();
            const newTime = Math.min(duration, wavesurfer.getCurrentTime() + 5);
            wavesurfer.seekTo(newTime / duration);
        }});

        // Update button text when play state changes
        wavesurfer.on('play', () => {{
            playPauseBtn.textContent = 'Pause';
        }});

        wavesurfer.on('pause', () => {{
            playPauseBtn.textContent = 'Play';
        }});

        volumeSlider.addEventListener('input', (e) => {{
            wavesurfer.setVolume(e.target.value / 100);
        }});

        // Save changes to CUE file
        saveBtn.addEventListener('click', async () => {{
            if (Object.keys(pendingChanges).length === 0) return;

            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';

            try {{
                const response = await fetch('/update-timestamps', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        cue_file: CUE_FILE,
                        updates: pendingChanges
                    }})
                }});

                if (response.ok) {{
                    // Clear pending changes
                    for (const key in pendingChanges) {{
                        delete pendingChanges[key];
                    }}
                    clearStorage();  // Clear localStorage on successful save
                    updateSaveButton();
                    statusEl.textContent = 'Saved! Refresh Marimo to see changes.';
                    statusEl.className = 'status saved';
                }} else {{
                    throw new Error('Save failed');
                }}
            }} catch (err) {{
                statusEl.textContent = 'Save failed: ' + err.message;
                statusEl.className = 'status';
                saveBtn.disabled = false;
                saveBtn.textContent = `Save Changes (${{Object.keys(pendingChanges).length}})`;
            }}
        }});

        // Zoom with Shift + scroll wheel
        let currentZoom = 1;  // pixels per second (will be calculated on ready)
        wavesurfer.on('ready', () => {{
            // Calculate initial zoom based on container width and duration
            const container = document.getElementById('waveform');
            currentZoom = container.offsetWidth / wavesurfer.getDuration();
        }});

        document.getElementById('waveform').addEventListener('wheel', (e) => {{
            if (e.shiftKey) {{
                e.preventDefault();
                // Normalize scroll direction: up = negative deltaY = zoom in
                // This works with Mac natural scrolling where scroll up = deltaY negative
                const zoomIn = e.deltaY < 0;
                const factor = zoomIn ? 1.3 : 0.77;  // Zoom in = bigger factor, zoom out = smaller
                currentZoom = Math.max(5, Math.min(500, currentZoom * factor));
                wavesurfer.zoom(currentZoom);
            }}
        }}, {{ passive: false }});

        // Add Marker button - toggle drag selection mode
        addMarkerBtn.addEventListener('click', () => {{
            addMarkerMode = !addMarkerMode;
            if (addMarkerMode) {{
                addMarkerBtn.textContent = 'Cancel (Esc)';
                addMarkerBtn.classList.add('active');
                statusEl.textContent = 'Drag on waveform to mark a track boundary';
                statusEl.className = 'status';

                // Enable drag selection
                disableDragSelection = regions.enableDragSelection({{
                    color: 'rgba(245, 158, 11, 0.5)',  // amber
                }});
            }} else {{
                addMarkerBtn.textContent = '+ Add Marker';
                addMarkerBtn.classList.remove('active');
                statusEl.textContent = '';
                if (disableDragSelection) {{
                    disableDragSelection();
                    disableDragSelection = null;
                }}
            }}
        }});

        // Handle Escape key to cancel add marker mode
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape' && addMarkerMode) {{
                addMarkerBtn.click();
            }}
        }});

        // Handle new regions created by drag selection
        regions.on('region-created', (region) => {{
            if (!addMarkerMode) return;  // Only process regions created by user dragging

            // Find the highest existing track number
            const allRegions = regions.getRegions();
            let maxNum = 0;
            allRegions.forEach(r => {{
                const match = r.id.match(/track(\\d+)/);
                if (match) {{
                    maxNum = Math.max(maxNum, parseInt(match[1]));
                }}
            }});
            const newTrackNum = maxNum + 1;

            // Update the region with a proper ID and styling
            region.setOptions({{
                id: 'track' + newTrackNum,
                content: 'T' + newTrackNum,
                color: newTrackNum % 2 === 0 ? 'rgba(168, 85, 247, 0.35)' : 'rgba(99, 102, 241, 0.35)',
                drag: false,
                resize: true,
            }});

            // Store the change
            originalStarts[newTrackNum] = region.start;
            pendingChanges[newTrackNum] = region.start;
            updateSaveButton();
            saveToStorage();

            // Exit add marker mode
            addMarkerMode = false;
            addMarkerBtn.textContent = '+ Add Marker';
            addMarkerBtn.classList.remove('active');
            if (disableDragSelection) {{
                disableDragSelection();
                disableDragSelection = null;
            }}

            statusEl.textContent = `Added marker T${{newTrackNum}} at ${{formatTime(region.start)}}`;
            statusEl.className = 'status';
        }});
    </script>
</body>
</html>'''

        # Write player HTML to MFP_DIR
        player_path = MFP_DIR / "_player.html"
        player_path.write_text(wavesurfer_html)

        # Load iframe with cache bust
        _ep_name = cue_path.stem if cue_path else ""
        player_url = f"http://localhost:{AUDIO_SERVER_PORT}/_player.html?v={refresh_count}&ep={_ep_name}"
        iframe_html = f'<iframe src="{player_url}" style="width: 100%; height: 220px; border: none; border-radius: 8px;"></iframe>'
        waveform_widget = mo.Html(iframe_html)
    else:
        waveform_widget = mo.callout(
            mo.md("**No audio available** - no local MP3 or streaming URL found"),
            kind="warn"
        )

    waveform_widget
    return audio_source, cue_relative_path, is_streaming, player_path, player_url, refresh_count, regions_js, waveform_widget, wavesurfer_html


@app.cell
def _(preview_status):
    # Display preview generation status (if any)
    preview_status
    return


@app.cell
def _():
    import pandas as pd
    return (pd,)


@app.cell
def _(cue_data, cue_path, get_reference_files, mo, pd):
    # Create tracks table - selectable for editing
    if cue_data and cue_data['tracks']:
        _tracks_df = pd.DataFrame(cue_data['tracks'])

        # Check which tracks have references
        _refs = {}
        if cue_path:
            _sidecar = cue_path.parent / f"{cue_path.stem}.mp3.d"
            if _sidecar.exists():
                _refs = get_reference_files(_sidecar)

        # Add "ref" column - checkmark if reference exists
        _tracks_df['ref'] = _tracks_df['track'].apply(
            lambda t: '✓' if t in _refs else ''
        )

        # Display as a table - show all rows without pagination
        # Columns: track, performer, title, start, ref (on right)
        tracks_table = mo.ui.table(
            _tracks_df[['track', 'performer', 'title', 'start', 'ref']],
            label="Tracks",
            page_size=50,
            pagination=False,
            selection="single",
            show_column_summaries=False,
        )
    else:
        tracks_table = mo.md("*No tracks found*")

    tracks_table
    return (tracks_table,)


@app.cell
def _(AUDIO_SERVER_PORT, MFP_DIR, Path, cue_data, cue_path, get_reference_files, mo, tracks_table):
    # Edit interface for selected track
    if hasattr(tracks_table, 'value') and len(tracks_table.value) > 0:
        _selected = tracks_table.value.iloc[0]
        selected_track_num = int(_selected['track'])
        _current_start = _selected['start']

        edit_time = mo.ui.text(
            value=_current_start,
            label=f"Start time for Track {selected_track_num}",
            placeholder="MM:SS"
        )

        # Reference player - look for reference file in sidecar
        _ref_player = None
        if cue_path:
            # Sidecar is {cue_file}.d/ or for symlinked cues, {mp3_file}.d/
            # First try: cue_path.stem + ".mp3.d"
            sidecar_dir = cue_path.parent / f"{cue_path.stem}.mp3.d"
            if not sidecar_dir.exists():
                # Fallback: cue_path with .d suffix
                sidecar_dir = cue_path.parent / f"{cue_path.name}.d"

            refs = get_reference_files(sidecar_dir)
            if selected_track_num in refs:
                ref_file = Path(refs[selected_track_num])
                # Make path relative to MFP_DIR for serving via HTTP
                # Use the symlink path (not resolved) since HTTP server follows symlinks
                if ref_file.exists() or ref_file.is_symlink():
                    try:
                        # Get relative path from MFP_DIR (using symlink path, not resolved)
                        rel_path = ref_file.relative_to(MFP_DIR)
                        _ref_audio_url = f"http://localhost:{AUDIO_SERVER_PORT}/{rel_path}"
                        _ref_player = mo.vstack([
                            mo.md(f"**Reference:** `{ref_file.name}`"),
                            mo.Html(f'<audio controls src="{_ref_audio_url}" style="width: 100%;"></audio>')
                        ])
                    except ValueError:
                        # File not under MFP_DIR
                        _ref_player = mo.md(f"*Reference found but not servable: {ref_file.name}*")

        edit_panel = mo.vstack([
            mo.md(f"### Edit Track {selected_track_num}: {_selected['title']}"),
            mo.md(f"**Artist:** {_selected['performer']}"),
            edit_time,
            mo.md("*Enter time as MM:SS (e.g., 03:45)*"),
            _ref_player,
        ])
    else:
        edit_panel = mo.callout(
            mo.md("Click a track row above to edit its timestamp"),
            kind="info"
        )
        edit_time = None
        selected_track_num = None

    edit_panel
    return edit_panel, edit_time, selected_track_num


@app.cell
def _(cue_data, cue_path, edit_time, mo, selected_track_num):
    # Generate updated CUE content
    def _time_to_cue_index(time_str):
        """Convert MM:SS to CUE format MM:SS:00"""
        parts = time_str.strip().split(':')
        if len(parts) == 2:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
        return time_str

    if edit_time and selected_track_num and cue_data:
        _new_time = edit_time.value

        # Generate updated CUE content
        _lines = []
        _lines.append(f'REM COMMENT "Music For Programming Episode 49"')
        _lines.append(f'TITLE "{cue_data["header"].get("title", "Unknown")}"')
        _lines.append(f'PERFORMER "{cue_data["header"].get("performer", "Unknown")}"')
        _lines.append(f'FILE "{cue_data["header"].get("file", "audio.wav")}" WAVE')

        for _trk in cue_data['tracks']:
            # Use new time if this is the edited track
            if _trk['track'] == selected_track_num:
                _cue_index = _time_to_cue_index(_new_time)
            else:
                _cue_index = _time_to_cue_index(_trk['start'])

            _lines.append(f'  TRACK {_trk["track"]:02d} AUDIO')
            _lines.append(f'    TITLE "{_trk["title"]}"')
            _lines.append(f'    PERFORMER "{_trk["performer"]}"')
            _lines.append(f'    INDEX 01 {_cue_index}')

        new_cue_content = '\n'.join(_lines) + '\n'

        # Find original time for this track
        _orig_track = next((_t for _t in cue_data['tracks'] if _t['track'] == selected_track_num), None)
        _orig_time = _orig_track['start'] if _orig_track else "??"

        # Preview the change
        save_info = mo.vstack([
            mo.md(f"**Preview:** Track {selected_track_num} start time: `{_orig_time}` → `{_new_time}`"),
            mo.md(f"**Target file:** `{cue_path}`"),
        ])
    else:
        save_info = mo.md("")
        new_cue_content = None

    save_info
    return new_cue_content, save_info


@app.cell
def _(mo, new_cue_content):
    # Save button - show when there are changes
    if new_cue_content:
        save_button = mo.ui.run_button(label="Save CUE File", kind="success")
    else:
        save_button = None

    save_button
    return (save_button,)


@app.cell
def _(cue_path, get_refresh, mo, new_cue_content, save_button, set_refresh):
    # Handle save action in separate cell
    save_result = None
    if save_button is not None and save_button.value and new_cue_content and cue_path:
        try:
            cue_path.write_text(new_cue_content)
            # Trigger refresh to re-parse the CUE file
            set_refresh(get_refresh() + 1)
            save_result = mo.callout(
                mo.md(f"Saved to `{cue_path.name}`"),
                kind="success"
            )
        except Exception as e:
            save_result = mo.callout(
                mo.md(f"**Error:** {e}"),
                kind="danger"
            )

    save_result
    return (save_result,)


@app.cell
def _(cue_data, cue_path, episode_name, is_draft, mfp_dir, mo):
    # Graduate button - show when a draft has all tracks with timestamps
    graduate_button = None
    graduate_info = None

    if is_draft and cue_data and cue_data.get('tracks'):
        # Check if all tracks have timestamps
        all_have_timestamps = all(t.get('has_timestamp', False) for t in cue_data['tracks'])

        if all_have_timestamps:
            # All tracks have timestamps - ready to graduate
            _new_cue_path = mfp_dir / f"{episode_name}.cue"
            graduate_button = mo.ui.run_button(
                label="📋 Graduate to Complete (.cue)",
                kind="success"
            )
            graduate_info = mo.md(f"""
**Ready to graduate!** All {len(cue_data['tracks'])} tracks have timestamps.

This will rename `{cue_path.name}` → `{episode_name}.cue`

The file will then be usable for chapter navigation during playback.
            """)
        else:
            # Not all tracks have timestamps
            tracks_with = sum(1 for t in cue_data['tracks'] if t.get('has_timestamp', False))
            tracks_total = len(cue_data['tracks'])
            graduate_info = mo.callout(
                mo.md(f"**Draft:** {tracks_with}/{tracks_total} tracks have timestamps. Add timestamps to all tracks to graduate."),
                kind="info"
            )

    if graduate_info:
        mo.vstack([graduate_info, graduate_button] if graduate_button else [graduate_info])
    return graduate_button, graduate_info


@app.cell
def _(cue_path, episode_name, get_refresh, graduate_button, is_draft, mfp_dir, mo, set_refresh):
    # Handle graduate action
    graduate_result = None
    if graduate_button is not None and graduate_button.value and is_draft and cue_path and mfp_dir:
        try:
            _graduated_path = mfp_dir / f"{episode_name}.cue"
            # Rename .cue-draft to .cue
            cue_path.rename(_graduated_path)
            # Trigger refresh
            set_refresh(get_refresh() + 1)
            graduate_result = mo.callout(
                mo.md(f"✅ Graduated! `{cue_path.name}` → `{_graduated_path.name}`\n\nRefresh the page to see the updated episode."),
                kind="success"
            )
        except Exception as e:
            graduate_result = mo.callout(
                mo.md(f"**Error graduating:** {e}"),
                kind="danger"
            )

    graduate_result
    return (graduate_result,)


if __name__ == "__main__":
    app.run()
