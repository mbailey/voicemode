#!/usr/bin/env python
"""
Simplified tests for voice-mode that don't require complex mocking.
"""

import pytest
import numpy as np
from pathlib import Path
import tempfile
import os


class TestSimpleAudioProcessing:
    """Test basic audio processing without mocking the entire system"""
    
    def test_audio_conversion(self):
        """Test audio data type conversions"""
        # Test int16 to float32 conversion
        int_samples = np.array([0, 16383, -16384, 32767, -32768], dtype=np.int16)
        float_samples = int_samples.astype(np.float32) / 32768.0
        
        # Check conversion bounds with tolerance for floating point precision
        assert float_samples.min() >= -1.0 or np.isclose(float_samples.min(), -1.0, atol=1e-6)
        assert float_samples.max() <= 1.0
        assert np.allclose(float_samples[0], 0.0)
        assert np.allclose(float_samples[3], 32767/32768.0, atol=0.001)
    
    def test_temp_file_creation(self):
        """Test temporary file handling"""
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(b'fake audio data')
        
        assert os.path.exists(tmp_path)
        assert tmp_path.endswith('.wav')
        
        # Cleanup
        os.unlink(tmp_path)
        assert not os.path.exists(tmp_path)
    
    def test_debug_directory_creation(self):
        """Test debug directory creation"""
        test_dir = Path.home() / "test-voice-mode-debug"
        
        # Create directory
        test_dir.mkdir(exist_ok=True)
        assert test_dir.exists()
        assert test_dir.is_dir()
        
        # Cleanup
        test_dir.rmdir()
        assert not test_dir.exists()


class TestConfiguration:
    """Test configuration and environment variables"""
    
    def test_env_var_parsing(self):
        """Test environment variable parsing"""
        # Test boolean parsing
        os.environ['TEST_BOOL_TRUE'] = 'true'
        os.environ['TEST_BOOL_FALSE'] = 'false'
        os.environ['TEST_BOOL_EMPTY'] = ''
        
        assert os.getenv('TEST_BOOL_TRUE', '').lower() == 'true'
        assert os.getenv('TEST_BOOL_FALSE', '').lower() == 'false'
        assert os.getenv('TEST_BOOL_EMPTY', '') == ''  # Empty env var returns empty string
        
        # Cleanup
        del os.environ['TEST_BOOL_TRUE']
        del os.environ['TEST_BOOL_FALSE']
        del os.environ['TEST_BOOL_EMPTY']
    
    def test_url_parsing(self):
        """Test URL format validation"""
        valid_urls = [
            'https://api.openai.com/v1',
            'http://127.0.0.1:2022/v1',
            'wss://example.livekit.cloud',
            'ws://127.0.0.1:7880'
        ]
        
        for url in valid_urls:
            assert url.startswith(('http://', 'https://', 'ws://', 'wss://'))
    
    def test_default_values(self):
        """Test default configuration values"""
        # Test default voice
        default_voice = os.getenv('TTS_VOICE', 'af_sky')
        assert default_voice in ['nova', 'alloy', 'echo', 'fable', 'onyx', 'shimmer', 'af_sky', 'af_bella', 'af_nicole', 'af_sarah', 'am_adam', 'am_michael', 'br_gabriel', 'kr_ji-woo', 'af_nova']
        
        # Test default models
        default_tts_model = os.getenv('TTS_MODEL', 'tts-1')
        assert default_tts_model in ['tts-1', 'tts-1-hd']
        
        default_stt_model = os.getenv('STT_MODEL', 'whisper-1')
        assert default_stt_model == 'whisper-1'


class TestUtilities:
    """Test utility functions"""
    
    def test_message_truncation(self):
        """Test message truncation for logging"""
        message = "This is a very long message that should be truncated for logging purposes"
        truncated = f"{message[:50]}{'...' if len(message) > 50 else ''}"
        
        assert truncated == "This is a very long message that should be truncat..."
        assert len(truncated) == 53  # 50 chars + 3 dots
    
    def test_file_path_validation(self):
        """Test file path validation"""
        # Test absolute paths
        test_paths = [
            Path.home() / "voice-mode_recordings",
            Path("/tmp/test-audio.wav"),
            Path.cwd() / "test.mp3"
        ]
        
        for path in test_paths:
            assert path.is_absolute() or path.parent.exists()
    
    @pytest.mark.asyncio
    async def test_async_operations(self):
        """Test basic async operations"""
        import asyncio
        
        # Test async sleep
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(0.1)
        end = asyncio.get_event_loop().time()
        
        assert (end - start) >= 0.1
        assert (end - start) < 0.2  # Allow some tolerance


# Integration test for MCP server
@pytest.mark.asyncio
async def test_mcp_server_import():
    """Test that we can import and create an MCP server"""
    try:
        from fastmcp import FastMCP
        
        # Create a simple test server
        test_mcp = FastMCP("test-server")
        
        # Add a simple tool
        @test_mcp.tool()
        async def test_tool(message: str) -> str:
            return f"Test response: {message}"
        
        # Verify the tool was added.
        # FastMCP 3.x: list_tools() is the public API (async, returns list).
        # FastMCP 2.x: _tool_manager._tools is the internal dict.
        if hasattr(test_mcp, 'list_tools'):
            tools = await test_mcp.list_tools()
        else:
            tools = test_mcp._tool_manager._tools
        assert len(tools) > 0
        
    except ImportError:
        pytest.skip("FastMCP not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])