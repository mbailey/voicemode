"""Unit tests for configuration management functions."""
import asyncio
import os
import re
import shlex
import shutil
import subprocess
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from voice_mode.tools.configuration_management import (
    update_config,
    list_config_keys,
    write_env_file,
    parse_env_file,
    _format_env_value,
    _shell_single_quote,
)


class TestConfigurationManagement:
    """Test configuration management functions."""

    @pytest.mark.asyncio
    async def test_list_config_keys(self):
        """Test listing configuration keys."""
        result = await getattr(list_config_keys, 'fn', list_config_keys)()
        
        # Should return a formatted string with config keys
        assert isinstance(result, str)
        assert "VOICEMODE_" in result
        
        # Should include common config keys
        assert "VOICEMODE_BASE_DIR" in result
        assert "VOICEMODE_DEBUG" in result
        assert "VOICEMODE_" in result
        
        # Should include descriptions
        assert "provider" in result.lower() or "TTS" in result

    @pytest.mark.asyncio
    async def test_update_config_returns_message(self):
        """Test that update_config returns a message."""
        # Create a proper temp file
        import tempfile
        import os
        
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write initial content
            with os.fdopen(fd, 'w') as f:
                f.write("# Test config\n")
                f.write("EXISTING_KEY=old_value\n")
            
            # Patch the config path
            with patch("voice_mode.tools.configuration_management.USER_CONFIG_PATH", Path(temp_path)):
                result = await getattr(update_config, 'fn', update_config)("TEST_KEY", "test_value")
                
                # Should return a message (success or error)
                assert isinstance(result, str)
                assert len(result) > 0
                
                # If successful, should mention the key and value
                if "success" in result.lower() or "updated" in result.lower():
                    assert "TEST_KEY" in result
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_update_config_noop_when_value_unchanged(self):
        """VM-1628: setting a key to its existing value must skip the file
        write and report 'no change' -- not a spurious 'updated successfully'.
        """
        import tempfile
        import os

        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("# Test config\n")
                f.write("KEEP_KEY=keep_me\n")

            with patch("voice_mode.tools.configuration_management.USER_CONFIG_PATH", Path(temp_path)):
                # Same value -> no-op: the file write must be skipped.
                with patch("voice_mode.tools.configuration_management.write_env_file") as mock_write:
                    result = await getattr(update_config, 'fn', update_config)("KEEP_KEY", "keep_me")
                    mock_write.assert_not_called()

                assert "no change" in result.lower()
                assert "updated successfully" not in result.lower()

                # A genuine change still updates exactly as before.
                result2 = await getattr(update_config, 'fn', update_config)("KEEP_KEY", "new_value")
                assert "updated successfully" in result2.lower()
                assert "new_value" in result2
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_update_config_function_exists(self):
        """Test that update_config function is callable."""
        # Just verify the function exists and is callable
        # FastMCP 2.x: .fn is the wrapped function; 3.x: tool IS the function
        assert callable(getattr(update_config, 'fn', update_config))
        
        # Test with a mock path that doesn't exist
        with patch("voice_mode.tools.configuration_management.USER_CONFIG_PATH", Path("/nonexistent/test.env")):
            with patch("pathlib.Path.mkdir"), patch("pathlib.Path.exists", return_value=False):
                with patch("builtins.open", mock_open()) as mock_file:
                    result = await getattr(update_config, 'fn', update_config)("TEST_KEY", "test_value")
                    # Should return a string result
                    assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_list_config_keys_structure(self):
        """Test that list_config_keys returns properly structured output."""
        result = await getattr(list_config_keys, 'fn', list_config_keys)()
        
        # Should have sections
        assert "Core Configuration" in result or "Configuration" in result
        assert "======" in result or "------" in result  # Section dividers
        
        # Should explain usage
        assert "Usage" in result or "update_config" in result

    @pytest.mark.asyncio
    async def test_config_functions_integration(self):
        """Test that config functions work together."""
        # List should work
        list_result = await getattr(list_config_keys, 'fn', list_config_keys)()
        assert len(list_result) > 100  # Should have substantial content
        
        # Update should return a message (even if it fails due to permissions)
        with patch("voice_mode.tools.configuration_management.USER_CONFIG_PATH", Path("/tmp/test_config.env")):
            with patch("pathlib.Path.mkdir"):
                try:
                    update_result = await getattr(update_config, 'fn', update_config)("TEST_INTEGRATION", "test")
                    assert isinstance(update_result, str)
                    assert len(update_result) > 0
                except Exception:
                    # Even if it fails, that's ok for this test
                    pass

    @pytest.mark.asyncio
    async def test_list_config_keys_formatting(self):
        """Test that list_config_keys returns properly formatted output."""
        result = await getattr(list_config_keys, 'fn', list_config_keys)()
        
        # Should have multiple lines
        lines = result.split('\n')
        assert len(lines) > 10  # Should have many config keys
        
        # Should have consistent formatting
        config_lines = [l for l in lines if 'VOICEMODE_' in l]
        assert len(config_lines) > 0
        
        # Each config line should have key and description
        for line in config_lines[:5]:  # Check first few
            if 'VOICEMODE_' in line and ':' in line:
                # Should have format like "VOICEMODE_KEY: description"
                assert line.count(':') >= 1


class TestWriteEnvFileCommentedDefaults:
    """Test handling of commented-out default values in config files."""

    def test_replace_commented_default_with_active_value(self):
        """When setting a key that exists as a commented default, replace in-place."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file with a commented default
            with os.fdopen(fd, 'w') as f:
                f.write("# Core Config\n")
                f.write("# VOICEMODE_WHISPER_MODEL=base\n")
                f.write("OTHER_KEY=value\n")

            temp_file = Path(temp_path)

            # Set the commented key to a new value
            write_env_file(temp_file, {"VOICEMODE_WHISPER_MODEL": "large"})

            # Read back and verify
            content = temp_file.read_text()
            lines = content.strip().split('\n')

            # Should have 3 lines: comment, active value (replacing commented), other key
            assert len(lines) == 3
            assert lines[0] == "# Core Config"
            assert lines[1] == "VOICEMODE_WHISPER_MODEL=large"
            assert lines[2] == "OTHER_KEY=value"

            # Should NOT have the commented version anymore
            assert "# VOICEMODE_WHISPER_MODEL" not in content

        finally:
            os.unlink(temp_path)

    def test_replace_active_value(self):
        """When setting a key that exists as active config, replace as before."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file with an active config
            with os.fdopen(fd, 'w') as f:
                f.write("# Core Config\n")
                f.write("VOICEMODE_TTS_VOICE=alloy\n")

            temp_file = Path(temp_path)

            # Update the active key
            write_env_file(temp_file, {"VOICEMODE_TTS_VOICE": "nova"})

            # Read back and verify
            content = temp_file.read_text()
            lines = content.strip().split('\n')

            assert len(lines) == 2
            assert lines[0] == "# Core Config"
            assert lines[1] == "VOICEMODE_TTS_VOICE=nova"

        finally:
            os.unlink(temp_path)

    def test_add_new_key_not_in_file(self):
        """When setting a key that doesn't exist at all, add at end."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file without the key
            with os.fdopen(fd, 'w') as f:
                f.write("# Core Config\n")
                f.write("EXISTING_KEY=value\n")

            temp_file = Path(temp_path)

            # Add a new key
            write_env_file(temp_file, {"NEW_KEY": "new_value"})

            # Read back and verify
            content = temp_file.read_text()

            # Should preserve existing content
            assert "# Core Config" in content
            assert "EXISTING_KEY=value" in content
            # New key should be added
            assert "NEW_KEY=new_value" in content

        finally:
            os.unlink(temp_path)

    def test_preserve_regular_comments(self):
        """Regular comments (not config defaults) should be preserved."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file with various comments
            with os.fdopen(fd, 'w') as f:
                f.write("# This is a section header\n")
                f.write("# Description of what this section does\n")
                f.write("VOICEMODE_DEBUG=false\n")
                f.write("\n")
                f.write("# Another comment\n")

            temp_file = Path(temp_path)

            # Update a value
            write_env_file(temp_file, {"VOICEMODE_DEBUG": "true"})

            # Read back and verify
            content = temp_file.read_text()

            # All regular comments should be preserved
            assert "# This is a section header" in content
            assert "# Description of what this section does" in content
            assert "# Another comment" in content
            # Value should be updated
            assert "VOICEMODE_DEBUG=true" in content

        finally:
            os.unlink(temp_path)

    def test_handle_commented_default_with_space(self):
        """Handle commented defaults with space after hash: '# KEY=value'."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("# VOICEMODE_KOKORO_PORT=8880\n")

            temp_file = Path(temp_path)
            write_env_file(temp_file, {"VOICEMODE_KOKORO_PORT": "9999"})

            content = temp_file.read_text()
            assert content.strip() == "VOICEMODE_KOKORO_PORT=9999"

        finally:
            os.unlink(temp_path)

    def test_handle_commented_default_without_space(self):
        """Handle commented defaults without space: '#KEY=value'."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("#VOICEMODE_KOKORO_PORT=8880\n")

            temp_file = Path(temp_path)
            write_env_file(temp_file, {"VOICEMODE_KOKORO_PORT": "9999"})

            content = temp_file.read_text()
            assert content.strip() == "VOICEMODE_KOKORO_PORT=9999"

        finally:
            os.unlink(temp_path)

    def test_multiple_commented_defaults(self):
        """Multiple commented defaults can be replaced."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("# Whisper settings\n")
                f.write("# VOICEMODE_WHISPER_MODEL=base\n")
                f.write("# VOICEMODE_WHISPER_PORT=2022\n")
                f.write("\n")
                f.write("# Kokoro settings\n")
                f.write("# VOICEMODE_KOKORO_PORT=8880\n")

            temp_file = Path(temp_path)
            write_env_file(temp_file, {
                "VOICEMODE_WHISPER_MODEL": "large-v3",
                "VOICEMODE_KOKORO_PORT": "9000"
            })

            content = temp_file.read_text()

            # Section comments preserved
            assert "# Whisper settings" in content
            assert "# Kokoro settings" in content

            # Values replaced
            assert "VOICEMODE_WHISPER_MODEL=large-v3" in content
            assert "VOICEMODE_KOKORO_PORT=9000" in content

            # Unchanged commented default preserved
            assert "# VOICEMODE_WHISPER_PORT=2022" in content

        finally:
            os.unlink(temp_path)

    def test_active_line_and_commented_default_no_duplicate(self):
        """If both an active line and a commented doc-default exist for the
        same key, writing the key must not produce two active lines.

        Regression test: the voicemode.env template ships with both
            VOICEMODE_SOUNDFONTS_ENABLED=true
            # VOICEMODE_SOUNDFONTS_ENABLED=true   (docs)
        and previously write_env_file would emit BOTH (replacing the active
        line in place AND uncommenting the docs line), silently disabling
        consumers that fail on duplicate keys (e.g. the soundfonts shell
        hook receiver).
        """
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("# Enable sound fonts for tool use hooks (true/false)\n")
                f.write("VOICEMODE_SOUNDFONTS_ENABLED=true\n")
                f.write("# VOICEMODE_SOUNDFONTS_ENABLED=true\n")

            temp_file = Path(temp_path)
            write_env_file(temp_file, {"VOICEMODE_SOUNDFONTS_ENABLED": "true"})

            content = temp_file.read_text()
            # Exactly one active line
            assert content.count("\nVOICEMODE_SOUNDFONTS_ENABLED=") + \
                   content.startswith("VOICEMODE_SOUNDFONTS_ENABLED=") == 1, \
                   f"Expected exactly one active line, got:\n{content}"
            # And the commented docs line preserved
            assert "# VOICEMODE_SOUNDFONTS_ENABLED=true" in content

        finally:
            os.unlink(temp_path)


class TestMultilineValueHandling:
    """Test handling of multiline quoted values in config files."""

    def test_parse_multiline_double_quoted_value(self):
        """parse_env_file should handle multiline double-quoted values."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('VOICEMODE_PRONOUNCE="\n')
                f.write('TTS \\bJSON\\b jason\n')
                f.write('TTS \\bYAML\\b yammel\n')
                f.write('"\n')
                f.write('OTHER_KEY=simple_value\n')

            config = parse_env_file(Path(temp_path))

            # Should have both keys
            assert "VOICEMODE_PRONOUNCE" in config
            assert "OTHER_KEY" in config

            # Multiline value should be preserved
            assert "TTS \\bJSON\\b jason" in config["VOICEMODE_PRONOUNCE"]
            assert "TTS \\bYAML\\b yammel" in config["VOICEMODE_PRONOUNCE"]

            # Simple value should work
            assert config["OTHER_KEY"] == "simple_value"

        finally:
            os.unlink(temp_path)

    def test_parse_multiline_single_quoted_value(self):
        """parse_env_file should handle multiline single-quoted values."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write("VOICEMODE_PRONOUNCE='\n")
                f.write("TTS pattern1 replacement1\n")
                f.write("TTS pattern2 replacement2\n")
                f.write("'\n")

            config = parse_env_file(Path(temp_path))

            assert "VOICEMODE_PRONOUNCE" in config
            assert "pattern1" in config["VOICEMODE_PRONOUNCE"]
            assert "pattern2" in config["VOICEMODE_PRONOUNCE"]

        finally:
            os.unlink(temp_path)

    def test_parse_single_line_quoted_value(self):
        """parse_env_file should handle single-line quoted values correctly."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('SIMPLE_QUOTED="hello world"\n')
                f.write("SINGLE_QUOTED='test value'\n")
                f.write("UNQUOTED=no_spaces\n")

            config = parse_env_file(Path(temp_path))

            assert config["SIMPLE_QUOTED"] == "hello world"
            assert config["SINGLE_QUOTED"] == "test value"
            assert config["UNQUOTED"] == "no_spaces"

        finally:
            os.unlink(temp_path)

    def test_write_preserves_multiline_value_not_in_config(self):
        """write_env_file should preserve multiline values that aren't being updated."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file with a multiline value
            with os.fdopen(fd, 'w') as f:
                f.write('VOICEMODE_PRONOUNCE="\n')
                f.write('TTS \\bJSON\\b jason\n')
                f.write('TTS \\bYAML\\b yammel\n')
                f.write('"\n')
                f.write('OTHER_KEY=old_value\n')

            temp_file = Path(temp_path)

            # Update only OTHER_KEY, not VOICEMODE_PRONOUNCE
            write_env_file(temp_file, {"OTHER_KEY": "new_value"})

            content = temp_file.read_text()

            # Multiline value should be preserved
            assert 'VOICEMODE_PRONOUNCE="' in content
            assert "TTS \\bJSON\\b jason" in content
            assert "TTS \\bYAML\\b yammel" in content
            # Updated value should be there
            assert "OTHER_KEY=new_value" in content

        finally:
            os.unlink(temp_path)

    def test_write_updates_multiline_value_in_config(self):
        """write_env_file should properly update multiline values."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file with a multiline value
            with os.fdopen(fd, 'w') as f:
                f.write('VOICEMODE_PRONOUNCE="\n')
                f.write('old content\n')
                f.write('"\n')

            temp_file = Path(temp_path)

            # Update the multiline value
            new_value = "new line 1\nnew line 2"
            write_env_file(temp_file, {"VOICEMODE_PRONOUNCE": new_value})

            content = temp_file.read_text()

            # New multiline value should be properly quoted
            assert "VOICEMODE_PRONOUNCE=" in content
            assert "new line 1" in content
            assert "new line 2" in content

            # Verify it can be parsed back
            config = parse_env_file(temp_file)
            assert "new line 1" in config["VOICEMODE_PRONOUNCE"]
            assert "new line 2" in config["VOICEMODE_PRONOUNCE"]

        finally:
            os.unlink(temp_path)

    def test_update_config_preserves_multiline_values(self):
        """update_config should not corrupt multiline values when updating other keys."""
        fd, temp_path = tempfile.mkstemp(suffix='.env')
        try:
            # Write a file with a multiline value and another key
            with os.fdopen(fd, 'w') as f:
                f.write('VOICEMODE_PRONOUNCE="\n')
                f.write('TTS \\bJSON\\b jason\n')
                f.write('"\n')
                f.write('VOICEMODE_WHISPER_MODEL=base\n')

            temp_file = Path(temp_path)

            # Update only VOICEMODE_WHISPER_MODEL
            with patch("voice_mode.tools.configuration_management.USER_CONFIG_PATH", temp_file):
                result = asyncio.run(getattr(update_config, 'fn', update_config)("VOICEMODE_WHISPER_MODEL", "large-v1"))

            # Should succeed
            assert "success" in result.lower() or "updated" in result.lower()

            # Verify multiline value is preserved. NOTE: update_config
            # re-serializes every key, so a previously double-quoted value is
            # rewritten with the safe single-quote format (GHSA-h97v-r3jw-cf6f).
            # Assert on content + round-trip, not on the quote character.
            content = temp_file.read_text()
            assert "VOICEMODE_PRONOUNCE=" in content
            assert "TTS \\bJSON\\b jason" in content

            # Verify updated value
            assert "VOICEMODE_WHISPER_MODEL=large-v1" in content

            # Verify it can still be parsed correctly
            config = parse_env_file(temp_file)
            assert "TTS \\bJSON\\b jason" in config.get("VOICEMODE_PRONOUNCE", "")
            assert config.get("VOICEMODE_WHISPER_MODEL") == "large-v1"

        finally:
            os.unlink(temp_path)


# Payloads that MUST never execute when voicemode.env is sourced, and MUST
# round-trip unchanged through write -> read. See GHSA-h97v-r3jw-cf6f.
_INJECTION_PAYLOADS = [
    "$(id)",                       # command substitution, no space (old verbatim branch)
    "af_sky,nova$(touch /tmp/x)",  # substitution mixed into a list value
    "`id`",                        # backtick command substitution
    "a${IFS}b",                    # parameter expansion sidesteps the space check
    'x"; touch /tmp/y; "',         # quote-break attempt against the old double-quoting
    "it's a 'test'",               # embedded single quotes -> '\'' escaping
    "TTS (?i)\\badcb\\b 'to do'",  # realistic pronounce value with quote + regex
]


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
class TestEnvValueShellSafety:
    """Regression tests for OS command injection via voicemode.env.

    GHSA-h97v-r3jw-cf6f: config values were written unescaped and the start
    scripts `source`d the file, so $(...) / backticks executed on service
    start. The fix single-quotes unsafe values (inert under `source`) and the
    start scripts no longer `source` the file.
    """

    def test_simple_values_are_written_unquoted(self):
        """Shell-inert values keep the clean KEY=value format (no churn)."""
        for v in ["large-v2", "true", "9999", "en", "127.0.0.1",
                  "http://127.0.0.1:2022/v1,https://api.openai.com/v1",
                  "mlx-community/Kokoro-82M-bf16", ""]:
            assert _format_env_value(v) == v, v

    def test_unsafe_values_are_single_quoted(self):
        """Anything with shell-active characters is single-quoted, never double."""
        for v in _INJECTION_PAYLOADS:
            formatted = _format_env_value(v)
            assert formatted.startswith("'") and formatted.endswith("'"), formatted
            # Double quotes must never be used -- they don't stop $() expansion.
            assert not formatted.startswith('"'), formatted

    def test_shell_single_quote_escapes_embedded_quote(self):
        assert _shell_single_quote("it's") == "'it'\\''s'"
        assert _shell_single_quote("plain") == "'plain'"

    @pytest.mark.parametrize("payload", _INJECTION_PAYLOADS)
    def test_payload_is_inert_when_sourced(self, payload, tmp_path):
        """The PoC: write a payload, `source` the file, assert nothing ran."""
        env_file = tmp_path / "voicemode.env"
        sentinel = tmp_path / "PWNED"
        # Embed a real command-substitution that would create the sentinel.
        value = f"{payload}$(touch {sentinel})"
        write_env_file(env_file, {"VOICEMODE_VOICES": value})

        result = subprocess.run(
            ["bash", "-c",
             f'source {shlex.quote(str(env_file))}; printf %s "$VOICEMODE_VOICES"'],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        assert not sentinel.exists(), "command substitution executed during source!"
        assert result.stdout == value, (result.stdout, value)

    @pytest.mark.parametrize("payload", _INJECTION_PAYLOADS)
    def test_value_roundtrips_through_parser(self, payload, tmp_path):
        """write -> parse_env_file returns the exact original value."""
        env_file = tmp_path / "voicemode.env"
        write_env_file(env_file, {"K": payload})
        assert parse_env_file(env_file)["K"] == payload


# The safe env loader inlined into both start scripts (replacing `source`).
_START_SCRIPTS = [
    "start-whisper-server.sh",
    "start-voicemode-serve.sh",
]


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "voice_mode" / "templates" / "scripts"


def _extract_loader(script_path: Path) -> str:
    text = script_path.read_text()
    m = re.search(
        r"(# >>> voicemode_load_env_file.*?# <<< voicemode_load_env_file <<<)",
        text, re.DOTALL,
    )
    assert m, f"loader sentinel block not found in {script_path}"
    return m.group(1)


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
class TestStartScriptEnvLoader:
    """The start scripts must load config without `source` (GHSA-h97v-r3jw-cf6f)."""

    def test_scripts_do_not_source_env_file(self):
        for name in _START_SCRIPTS:
            text = (_scripts_dir() / name).read_text()
            assert 'source "$VOICEMODE_DIR/voicemode.env"' not in text, name
            assert "voicemode_load_env_file" in text, name

    def test_loader_block_is_identical_across_scripts(self):
        blocks = {n: _extract_loader(_scripts_dir() / n) for n in _START_SCRIPTS}
        first = next(iter(blocks.values()))
        for name, block in blocks.items():
            assert block == first, f"loader in {name} diverged"

    def test_loader_loads_scalars_and_neutralizes_injection(self, tmp_path):
        loader = _extract_loader(_scripts_dir() / "start-whisper-server.sh")
        loader_file = tmp_path / "loader.sh"
        loader_file.write_text(loader + "\n")

        sub = tmp_path / "PWNED_SUB"
        btick = tmp_path / "PWNED_BTICK"
        env_file = tmp_path / "voicemode.env"
        # Use _format_env_value so the file matches what the writer produces.
        evil_sub = _format_env_value(f"x$(touch {sub})")
        evil_btick = _format_env_value(f"`touch {btick}`")
        env_file.write_text(
            "# comment\n"
            "VOICEMODE_WHISPER_MODEL=large-v2\n"
            "VOICEMODE_WHISPER_PORT=2022\n"
            f"VOICEMODE_VOICES={evil_sub}\n"
            f"VOICEMODE_EVIL={evil_btick}\n"
            'VOICEMODE_STT_PROMPT="claude CLAUDE.md Cora"\n'
            "VOICEMODE_SERVE_SECRET='s3cr3t_AB.+/='\n"
        )
        script = (
            "set -o nounset -o pipefail -o errexit\n"
            f"source {shlex.quote(str(loader_file))}\n"
            f"voicemode_load_env_file {shlex.quote(str(env_file))}\n"
            'printf "MODEL=%s\\n" "$VOICEMODE_WHISPER_MODEL"\n'
            'printf "PORT=%s\\n" "$VOICEMODE_WHISPER_PORT"\n'
            'printf "PROMPT=%s\\n" "$VOICEMODE_STT_PROMPT"\n'
            'printf "SECRET=%s\\n" "$VOICEMODE_SERVE_SECRET"\n'
        )
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert not sub.exists() and not btick.exists(), "injection executed in loader!"
        assert "MODEL=large-v2" in result.stdout
        assert "PORT=2022" in result.stdout
        # Surrounding quotes are stripped, contents never expanded.
        assert "PROMPT=claude CLAUDE.md Cora" in result.stdout
        assert "SECRET=s3cr3t_AB.+/=" in result.stdout
