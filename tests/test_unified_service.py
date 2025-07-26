"""
Tests for the unified service management tool
"""
import os
import sys
import platform
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import pytest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the service function
from voice_mode.tools.service import service


class TestUnifiedServiceTool:
    """Test cases for the unified service management tool"""
    
    @pytest.mark.asyncio
    async def test_status_service_not_running(self):
        """Test status when service is not running"""
        with patch('voice_mode.tools.service.find_process_by_port', return_value=None):
            result = await service("whisper", "status")
            assert "not running" in result.lower()
            assert "port 2022" in result
    
    @pytest.mark.asyncio
    async def test_status_service_running(self):
        """Test status when service is running"""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.oneshot.return_value.__enter__.return_value = None
        mock_proc.cpu_percent.return_value = 15.5
        mock_proc.memory_info.return_value = MagicMock(rss=100 * 1024 * 1024)  # 100 MB
        mock_proc.create_time.return_value = 1000000000
        mock_proc.cmdline.return_value = ["whisper-server", "--model", "model.bin"]
        
        with patch('voice_mode.tools.service.find_process_by_port', return_value=mock_proc), \
             patch('time.time', return_value=1000001000):  # 1000 seconds later
            result = await service("whisper", "status")
            assert "✅" in result
            assert "is running" in result
            assert "PID: 12345" in result
            assert "CPU: 15.5%" in result
            assert "Memory: 100.0 MB" in result
            assert "16m 40s" in result  # uptime
    
    @pytest.mark.asyncio
    async def test_start_service_already_running(self):
        """Test starting a service that's already running"""
        mock_proc = MagicMock()
        with patch('voice_mode.tools.service.find_process_by_port', return_value=mock_proc):
            result = await service("kokoro", "start")
            assert "already running" in result
    
    @pytest.mark.asyncio
    async def test_start_whisper_service(self):
        """Test starting whisper service"""
        with patch('voice_mode.tools.service.find_process_by_port', side_effect=[None, MagicMock()]), \
             patch('voice_mode.tools.service.find_whisper_server', return_value="/path/to/whisper-server"), \
             patch('voice_mode.tools.service.find_whisper_model', return_value="/path/to/model.bin"), \
             patch('subprocess.Popen') as mock_popen, \
             patch('asyncio.sleep'):
            
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.pid = 12345
            mock_popen.return_value = mock_process
            
            result = await service("whisper", "start")
            assert "✅" in result
            assert "started successfully" in result
            assert "PID: 12345" in result
    
    @pytest.mark.asyncio
    async def test_start_whisper_missing_binary(self):
        """Test starting whisper when binary is missing"""
        with patch('voice_mode.tools.service.find_process_by_port', return_value=None), \
             patch('voice_mode.tools.service.find_whisper_server', return_value=None):
            result = await service("whisper", "start")
            assert "❌" in result
            assert "not found" in result
            assert "whisper_install" in result
    
    @pytest.mark.asyncio
    async def test_stop_service_not_running(self):
        """Test stopping a service that's not running"""
        with patch('voice_mode.tools.service.find_process_by_port', return_value=None):
            result = await service("whisper", "stop")
            assert "not running" in result
    
    @pytest.mark.asyncio
    async def test_stop_service_success(self):
        """Test successfully stopping a service"""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.terminate = MagicMock()
        mock_proc.wait = MagicMock()
        
        with patch('voice_mode.tools.service.find_process_by_port', return_value=mock_proc):
            result = await service("kokoro", "stop")
            assert "✅" in result
            assert "stopped" in result
            assert "was PID: 12345" in result
            mock_proc.terminate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_restart_service(self):
        """Test restarting a service"""
        with patch('voice_mode.tools.service.stop_service', return_value="✅ Service stopped"), \
             patch('voice_mode.tools.service.start_service', return_value="✅ Service started"), \
             patch('asyncio.sleep'):
            result = await service("whisper", "restart")
            assert "Restart whisper:" in result
            assert "✅ Service stopped" in result
            assert "✅ Service started" in result
    
    @pytest.mark.asyncio
    async def test_enable_service_macos(self):
        """Test enabling service on macOS"""
        with patch('platform.system', return_value='Darwin'), \
             patch('voice_mode.tools.service.get_installed_service_version', return_value="1.0.0"), \
             patch('voice_mode.tools.service.load_service_file_version', return_value="1.0.0"), \
             patch('voice_mode.tools.service.load_service_template', return_value="template content"), \
             patch('voice_mode.tools.service.find_whisper_server', return_value="/path/to/whisper"), \
             patch('voice_mode.tools.service.find_whisper_model', return_value="/path/to/model.bin"), \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.write_text'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await service("whisper", "enable")
            assert "✅" in result
            assert "enabled" in result
            assert "will start automatically at login" in result
    
    @pytest.mark.asyncio
    async def test_enable_service_linux(self):
        """Test enabling service on Linux"""
        with patch('platform.system', return_value='Linux'), \
             patch('voice_mode.tools.service.get_installed_service_version', return_value="1.0.0"), \
             patch('voice_mode.tools.service.load_service_file_version', return_value="1.0.0"), \
             patch('voice_mode.tools.service.load_service_template', return_value="template content"), \
             patch('voice_mode.tools.service.find_kokoro_fastapi', return_value="/path/to/kokoro"), \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.write_text'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await service("kokoro", "enable")
            assert "✅" in result
            assert "enabled and started" in result
            
            # Verify systemctl commands were called
            assert any("daemon-reload" in str(call) for call in mock_run.call_args_list)
            assert any("enable" in str(call) for call in mock_run.call_args_list)
            assert any("start" in str(call) for call in mock_run.call_args_list)
    
    @pytest.mark.asyncio
    async def test_disable_service_macos(self):
        """Test disabling service on macOS"""
        with patch('platform.system', return_value='Darwin'), \
             patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.unlink'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0)
            
            result = await service("whisper", "disable")
            assert "✅" in result
            assert "disabled and removed" in result
    
    @pytest.mark.asyncio
    async def test_disable_service_not_installed(self):
        """Test disabling service that's not installed"""
        with patch('platform.system', return_value='Darwin'), \
             patch('pathlib.Path.exists', return_value=False):
            
            result = await service("whisper", "disable")
            assert "not installed" in result
    
    @pytest.mark.asyncio
    async def test_view_logs_macos(self):
        """Test viewing logs on macOS"""
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run') as mock_run:
            
            log_output = "2024-01-15 10:00:00 whisper-server started\n2024-01-15 10:00:01 Listening on port 2022"
            mock_run.return_value = MagicMock(returncode=0, stdout=log_output)
            
            result = await service("whisper", "logs", lines=10)
            assert "Last 10 log entries" in result
            assert "whisper-server started" in result
            assert "Listening on port 2022" in result
    
    @pytest.mark.asyncio
    async def test_view_logs_linux(self):
        """Test viewing logs on Linux"""
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.run') as mock_run:
            
            journal_output = "Jan 15 10:00:00 systemd[1]: Started voicemode-kokoro.service"
            mock_run.return_value = MagicMock(returncode=0, stdout=journal_output)
            
            result = await service("kokoro", "logs", lines=20)
            assert "Last 20 journal entries" in result
            assert "Started voicemode-kokoro.service" in result
    
    @pytest.mark.asyncio
    async def test_view_logs_fallback_to_files(self):
        """Test fallback to log files when system logs unavailable"""
        with patch('platform.system', return_value='Darwin'), \
             patch('subprocess.run') as mock_run, \
             patch('pathlib.Path.exists', side_effect=[True, True]), \
             patch('builtins.open', mock_open(read_data="Log line 1\nLog line 2\n")):
            
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            
            result = await service("whisper", "logs")
            assert "stdout" in result
            assert "Log line 1" in result
            assert "Log line 2" in result
    
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        """Test invalid action handling"""
        result = await service("whisper", "invalid_action")  # type: ignore
        assert "❌" in result
        assert "Unknown action" in result
    
    @pytest.mark.asyncio
    async def test_version_update_detection(self):
        """Test that version updates are detected when enabling"""
        with patch('platform.system', return_value='Darwin'), \
             patch('voice_mode.tools.service.get_installed_service_version', return_value="1.0.0"), \
             patch('voice_mode.tools.service.load_service_file_version', return_value="1.1.0"), \
             patch('voice_mode.tools.service.load_service_template', return_value="template"), \
             patch('voice_mode.tools.service.find_whisper_server', return_value="/path/to/whisper"), \
             patch('voice_mode.tools.service.find_whisper_model', return_value="/path/to/model.bin"), \
             patch('pathlib.Path.mkdir'), \
             patch('pathlib.Path.write_text'), \
             patch('subprocess.run') as mock_run, \
             patch('logging.Logger.info') as mock_log:
            
            mock_run.return_value = MagicMock(returncode=0)
            
            await service("whisper", "enable")
            
            # Verify version update was logged
            mock_log.assert_any_call("Service file update available: 1.0.0 -> 1.1.0")


class TestServicePrompts:
    """Test service-specific prompts"""
    
    def test_whisper_prompt_valid_action(self):
        """Test whisper prompt with valid action"""
        from voice_mode.prompts.services import whisper_prompt
        
        result = whisper_prompt("status")
        assert "service tool" in result
        assert "service_name='whisper'" in result
        assert "action='status'" in result
    
    def test_whisper_prompt_logs_action(self):
        """Test whisper prompt for logs action"""
        from voice_mode.prompts.services import whisper_prompt
        
        result = whisper_prompt("logs")
        assert "service tool" in result
        assert "action='logs'" in result
        assert "view recent logs" in result
    
    def test_whisper_prompt_invalid_action(self):
        """Test whisper prompt with invalid action"""
        from voice_mode.prompts.services import whisper_prompt
        
        result = whisper_prompt("invalid")
        assert "Invalid action" in result
        assert "Use one of:" in result
    
    def test_kokoro_prompt_valid_action(self):
        """Test kokoro prompt with valid action"""
        from voice_mode.prompts.services import kokoro_prompt
        
        result = kokoro_prompt("start")
        assert "service tool" in result
        assert "service_name='kokoro'" in result
        assert "action='start'" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])