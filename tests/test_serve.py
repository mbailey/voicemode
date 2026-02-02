"""Unit tests for the VoiceMode serve command.

Tests for:
- Default transport is streamable-http
- --transport sse selects SSE
- Deprecation warning appears for SSE
- Environment variable VOICEMODE_SERVE_TRANSPORT is respected
- CLI --transport overrides environment variable
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


class TestServeTransportOption:
    """Tests for the serve command --transport option."""

    def test_serve_help_shows_transport_option(self):
        """Test that serve --help shows the transport option."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()
        result = runner.invoke(voice_mode_main_cli, ['serve', '--help'])

        assert result.exit_code == 0
        assert '--transport' in result.output or '-t' in result.output
        assert 'streamable-http' in result.output
        assert 'sse' in result.output
        assert 'deprecated' in result.output.lower()

    def test_default_transport_is_streamable_http(self):
        """Test that default transport is streamable-http."""
        # Clear any existing env var to test the default
        env_backup = os.environ.get("VOICEMODE_SERVE_TRANSPORT")
        try:
            # Remove env var if it exists
            if "VOICEMODE_SERVE_TRANSPORT" in os.environ:
                del os.environ["VOICEMODE_SERVE_TRANSPORT"]

            # Need to reimport to get fresh config values
            import importlib
            import voice_mode.config
            importlib.reload(voice_mode.config)

            assert voice_mode.config.SERVE_TRANSPORT == "streamable-http"
        finally:
            # Restore env var
            if env_backup is not None:
                os.environ["VOICEMODE_SERVE_TRANSPORT"] = env_backup

    def test_env_var_changes_default(self):
        """Test that VOICEMODE_SERVE_TRANSPORT env var is respected."""
        env_backup = os.environ.get("VOICEMODE_SERVE_TRANSPORT")
        try:
            os.environ["VOICEMODE_SERVE_TRANSPORT"] = "sse"
            import importlib
            import voice_mode.config
            importlib.reload(voice_mode.config)

            assert voice_mode.config.SERVE_TRANSPORT == "sse"
        finally:
            # Restore env var
            if env_backup is not None:
                os.environ["VOICEMODE_SERVE_TRANSPORT"] = env_backup
            elif "VOICEMODE_SERVE_TRANSPORT" in os.environ:
                del os.environ["VOICEMODE_SERVE_TRANSPORT"]
            # Reload to reset
            import importlib
            import voice_mode.config
            importlib.reload(voice_mode.config)

    def test_transport_option_streamable_http(self):
        """Test that --transport streamable-http uses /mcp path."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        # Create a mock for the mcp object that will be imported
        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        # Patch at the import location in voice_mode.cli
        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'streamable-http']
                )

                # Check output contains /mcp path
                assert '/mcp' in result.output
                # Check it says Transport: streamable-http
                assert 'streamable-http' in result.output

    def test_transport_option_sse(self):
        """Test that --transport sse uses /sse path."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'sse']
                )

                # Check output contains /sse path
                assert '/sse' in result.output

    def test_sse_transport_shows_deprecation_warning(self):
        """Test that using SSE transport shows deprecation warning."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'sse']
                )

                # Check output for the deprecation warning
                combined_output = result.output
                assert 'Warning' in combined_output or 'deprecated' in combined_output.lower()

    def test_streamable_http_no_deprecation_warning(self):
        """Test that using streamable-http does NOT show deprecation warning."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'streamable-http']
                )

                # Check that deprecation warning is NOT in output
                output = result.output
                assert 'SSE transport is deprecated' not in output

    def test_cli_transport_overrides_env_var(self):
        """Test that CLI --transport option overrides env var."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        # Set env var to streamable-http but use CLI to specify sse
        env_backup = os.environ.get("VOICEMODE_SERVE_TRANSPORT")
        try:
            os.environ["VOICEMODE_SERVE_TRANSPORT"] = "streamable-http"

            mock_mcp = MagicMock()
            mock_app = MagicMock()
            mock_mcp.http_app.return_value = mock_app

            with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
                with patch('uvicorn.run') as mock_uvicorn:
                    result = runner.invoke(
                        voice_mode_main_cli,
                        ['serve', '--transport', 'sse']
                    )

                    # CLI should override env var - output should show /sse
                    assert '/sse' in result.output
        finally:
            if env_backup is not None:
                os.environ["VOICEMODE_SERVE_TRANSPORT"] = env_backup
            elif "VOICEMODE_SERVE_TRANSPORT" in os.environ:
                del os.environ["VOICEMODE_SERVE_TRANSPORT"]

    def test_short_option_t_works(self):
        """Test that -t short option works for transport."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '-t', 'sse']
                )

                # Should work with short option and show /sse
                assert '/sse' in result.output

    def test_invalid_transport_rejected(self):
        """Test that invalid transport value is rejected."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        result = runner.invoke(
            voice_mode_main_cli,
            ['serve', '--transport', 'invalid-transport']
        )

        # Click should reject invalid choices
        assert result.exit_code != 0
        assert 'invalid-transport' in result.output.lower() or 'invalid' in result.output.lower()

    def test_transport_affects_displayed_endpoint(self):
        """Test that transport selection affects displayed endpoint path."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                # Test streamable-http shows /mcp
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'streamable-http']
                )
                assert '/mcp' in result.output

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                # Test sse shows /sse
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'sse']
                )
                assert '/sse' in result.output


class TestServeTransportWithSecret:
    """Tests for transport option combined with secret path."""

    def test_streamable_http_with_secret(self):
        """Test that streamable-http with secret uses /mcp/secret path."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'streamable-http', '--secret', 'mysecret']
                )

                # Output should show /mcp/mysecret
                assert '/mcp/mysecret' in result.output

    def test_sse_with_secret(self):
        """Test that sse with secret uses /sse/secret path."""
        from voice_mode.cli import voice_mode_main_cli

        runner = CliRunner()

        mock_mcp = MagicMock()
        mock_app = MagicMock()
        mock_mcp.http_app.return_value = mock_app

        with patch.dict('sys.modules', {'voice_mode.server': MagicMock(mcp=mock_mcp)}):
            with patch('uvicorn.run') as mock_uvicorn:
                result = runner.invoke(
                    voice_mode_main_cli,
                    ['serve', '--transport', 'sse', '--secret', 'mysecret']
                )

                # Output should show /sse/mysecret
                assert '/sse/mysecret' in result.output
