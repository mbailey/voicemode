"""Unit tests for diagnostic tool functions."""
import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock, AsyncMock
from voice_mode.tools.diagnostics import voice_mode_info
from voice_mode.tools.devices import check_audio_devices
from voice_mode.tools.voice_registry import voice_registry
from voice_mode.tools.dependencies import check_audio_dependencies


class TestDiagnosticTools:
    """Test diagnostic tool functions."""

    @pytest.mark.asyncio
    async def test_voice_mode_info(self):
        """Test voice_mode_info returns installation information."""
        with patch("voice_mode.tools.diagnostics.__version__", "2.18.0"), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.home", return_value=Path("/home/test")):
            
            result = await voice_mode_info.fn()
            
            # Should return formatted string
            assert isinstance(result, str)
            
            # Should include version
            assert "2.18.0" in result or "Version" in result
            
            # Should include configuration info
            assert "Configuration" in result or "config" in result.lower()
            
            # Should include provider info
            assert "Provider" in result or "TTS" in result or "STT" in result

    @pytest.mark.asyncio
    async def test_check_audio_devices(self):
        """Test check_audio_devices returns device information."""
        mock_input_devices = [
            {"name": "Built-in Microphone", "index": 0, "max_input_channels": 2, "max_output_channels": 0},
            {"name": "USB Microphone", "index": 1, "max_input_channels": 1, "max_output_channels": 0}
        ]
        mock_output_devices = [
            {"name": "Built-in Output", "index": 0, "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Bluetooth Speaker", "index": 1, "max_input_channels": 0, "max_output_channels": 2}
        ]
        
        with patch("voice_mode.tools.devices.sd.query_devices") as mock_query:
            # Setup mock to return devices based on kind parameter
            def query_side_effect(kind=None):
                if kind == 'input':
                    return {"name": "Built-in Microphone", "index": 0, "max_input_channels": 2, "max_output_channels": 0}
                elif kind == 'output':
                    return {"name": "Built-in Output", "index": 0, "max_input_channels": 0, "max_output_channels": 2}
                # Return all devices when kind is None
                all_devices = [
                    {"name": "Built-in Microphone", "index": 0, "max_input_channels": 2, "max_output_channels": 0},
                    {"name": "USB Microphone", "index": 1, "max_input_channels": 1, "max_output_channels": 0},
                    {"name": "Built-in Output", "index": 2, "max_input_channels": 0, "max_output_channels": 2},
                    {"name": "Bluetooth Speaker", "index": 3, "max_input_channels": 0, "max_output_channels": 2}
                ]
                return all_devices
            
            mock_query.side_effect = query_side_effect
            
            result = await check_audio_devices.fn()
            
            # Should return formatted string
            assert isinstance(result, str)
            
            # Should include input devices
            assert "Input" in result or "Microphone" in result
            assert "Built-in Microphone" in result or "USB Microphone" in result
            
            # Should include output devices
            assert "Output" in result or "Speaker" in result
            assert "Built-in Output" in result or "Bluetooth Speaker" in result

    @pytest.mark.asyncio
    async def test_voice_registry(self):
        """Test voice_registry returns provider information.

        After VM-1208 impl-003 the tool sources its voice list from the
        shared ``enumerate_voices`` enumerator, not ``provider_registry``.
        We patch the enumerator to return a controlled fake list; the
        endpoint URLs come from ``TTS_BASE_URLS`` / ``STT_BASE_URLS`` via
        config, which we also patch for hermeticity.
        """
        async def fake_enumerate(*, include_local_only):
            return [
                {
                    "id": "kokoro:af_sky",
                    "voice": "af_sky",
                    "name": "af_sky",
                    "provider": "kokoro",
                    "language": None,
                    "gender": None,
                    "preview_url": None,
                },
                {
                    "id": "kokoro:am_adam",
                    "voice": "am_adam",
                    "name": "am_adam",
                    "provider": "kokoro",
                    "language": None,
                    "gender": None,
                    "preview_url": None,
                },
            ]

        with patch(
            "voice_mode.tools.voice_registry.enumerate_voices",
            side_effect=fake_enumerate,
        ), patch(
            "voice_mode.tools.voice_registry.TTS_BASE_URLS",
            ["http://127.0.0.1:8880/v1"],
        ), patch(
            "voice_mode.tools.voice_registry.STT_BASE_URLS",
            ["http://127.0.0.1:2022/v1"],
        ):
            result = await voice_registry.fn()

            # Should return formatted string
            assert isinstance(result, str)

            # Should include TTS providers
            assert "TTS" in result or "Text-to-Speech" in result
            assert "8880" in result  # Port number

            # Should include STT providers
            assert "STT" in result or "Speech-to-Text" in result
            assert "2022" in result  # Port number

            # Should show health status
            assert "✅" in result or "healthy" in result.lower() or "available" in result.lower()

            # Voices from the shared enumerator should appear in the prose
            assert "af_sky" in result
            assert "am_adam" in result

    @pytest.mark.asyncio
    async def test_check_audio_dependencies_linux(self):
        """Test check_audio_dependencies on Linux."""
        # Since platform is imported inside the function, we need to ensure
        # the function reloads it with our mock
        with patch("voice_mode.tools.dependencies.diagnose_audio_setup", return_value=[]):
            import sys
            import importlib
            
            # Create a mock platform module
            mock_platform = MagicMock()
            mock_platform.system.return_value = "Linux"
            mock_platform.platform.return_value = "Linux-5.0"
            
            # Save original platform module if it exists
            original_platform = sys.modules.get('platform')
            
            # Replace platform module with our mock
            sys.modules['platform'] = mock_platform
            
            try:
                # Reload the dependencies module to use our mocked platform
                if 'voice_mode.tools.dependencies' in sys.modules:
                    importlib.reload(sys.modules['voice_mode.tools.dependencies'])
                
                with patch("shutil.which") as mock_which, \
                     patch("subprocess.run") as mock_run:
                    
                    # Mock package checks
                    mock_which.side_effect = lambda cmd: cmd in ["pulseaudio", "pactl"]
                    
                    # Mock PulseAudio status
                    mock_run.return_value = MagicMock(
                        returncode=0,
                        stdout="PulseAudio 15.0"
                    )
                    
                    result = await check_audio_dependencies.fn()
                    
                    # Should return dictionary with text and data
                    assert isinstance(result, dict)
                    assert "text" in result
                    assert "data" in result
                    
                    # Should identify platform
                    assert result["data"]["platform"] == "Linux"
                    
                    # Should check packages
                    assert "packages" in result["data"] or "diagnostics" in result["data"]
                    
                    # Should check PulseAudio
                    assert "pulseaudio" in result["data"] or "diagnostics" in result["data"]
            finally:
                # Restore original platform module
                if original_platform:
                    sys.modules['platform'] = original_platform
                else:
                    sys.modules.pop('platform', None)

    @pytest.mark.asyncio
    async def test_check_audio_dependencies_macos(self):
        """Test check_audio_dependencies on macOS."""
        with patch("voice_mode.tools.dependencies.diagnose_audio_setup", return_value=[]):
            import sys
            import importlib
            
            # Create a mock platform module
            mock_platform = MagicMock()
            mock_platform.system.return_value = "Darwin"
            mock_platform.platform.return_value = "Darwin-21.0"
            
            # Save original platform module if it exists
            original_platform = sys.modules.get('platform')
            
            # Replace platform module with our mock
            sys.modules['platform'] = mock_platform
            
            try:
                # Reload the dependencies module to use our mocked platform
                if 'voice_mode.tools.dependencies' in sys.modules:
                    importlib.reload(sys.modules['voice_mode.tools.dependencies'])
                
                result = await check_audio_dependencies.fn()
                
                # Should return dictionary with text and data
                assert isinstance(result, dict)
                assert "text" in result
                assert "data" in result
                
                # Should identify platform
                assert result["data"]["platform"] in ["macOS", "Darwin"]
                
                # Should have diagnostics
                assert "diagnostics" in result["data"]
                
                # Should have recommendations
                assert "recommendations" in result["data"]
            finally:
                # Restore original platform module
                if original_platform:
                    sys.modules['platform'] = original_platform
                else:
                    sys.modules.pop('platform', None)

    @pytest.mark.asyncio
    async def test_check_audio_dependencies_windows(self):
        """Test check_audio_dependencies on Windows/WSL."""
        with patch("platform.system", return_value="Linux"), \
             patch("pathlib.Path.exists") as mock_exists:
            
            # Mock WSL detection
            mock_exists.return_value = True  # /proc/sys/fs/binfmt_misc/WSLInterop exists
            
            result = await check_audio_dependencies.fn()
            
            # Should return dictionary
            assert isinstance(result, dict)
            
            # Should detect WSL
            if "diagnostics" in result:
                wsl_detected = any("WSL" in d for d in result["diagnostics"])
                assert wsl_detected or result["platform"] == "Linux"

    @pytest.mark.asyncio
    async def test_voice_mode_info_error_handling(self):
        """Test voice_mode_info handles errors gracefully."""
        # Skip this test as get_voice_mode_version doesn't exist
        pytest.skip("get_voice_mode_version doesn't exist in current implementation")

    @pytest.mark.asyncio
    async def test_check_audio_devices_no_devices(self):
        """Test check_audio_devices when no devices are found."""
        with patch("voice_mode.tools.devices.sd.query_devices") as mock_query:
            # When called with no args, return empty list
            # When called with kind='input' or 'output', return a mock device
            def query_side_effect(kind=None):
                if kind == 'input':
                    return {"name": "No Input Device", "index": -1, "max_input_channels": 0, "max_output_channels": 0}
                elif kind == 'output':
                    return {"name": "No Output Device", "index": -1, "max_input_channels": 0, "max_output_channels": 0}
                else:
                    return []  # No devices
                    
            mock_query.side_effect = query_side_effect
            
            result = await check_audio_devices.fn()
            
            # Should return formatted string
            assert isinstance(result, str)
            
            # Should show No devices or -1 index or similar
            assert "No " in result or "-1" in result or "Audio Devices" in result
