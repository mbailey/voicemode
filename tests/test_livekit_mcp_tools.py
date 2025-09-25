"""
Tests for LiveKit MCP tool registration and functionality
"""
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLiveKitMCPTools:
    """Test cases for LiveKit MCP tool registration"""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test infrastructure needs update for MCP API changes")
    async def test_livekit_tools_registered(self):
        """Test that all LiveKit tools are properly registered with MCP"""
        from voice_mode import server
        
        # Get all registered tools
        mcp_instance = server.mcp
        tools = mcp_instance.tools
        
        # Check that LiveKit tools are registered
        livekit_tools = [
            'livekit_install',
            'livekit_uninstall',
            'livekit_frontend_start',
            'livekit_frontend_stop',
            'livekit_frontend_status'
        ]
        
        registered_tool_names = [tool.name for tool in tools]
        
        for tool_name in livekit_tools:
            assert tool_name in registered_tool_names, f"Tool {tool_name} not registered"
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test infrastructure needs update for MCP API changes")
    async def test_livekit_install_tool_schema(self):
        """Test LiveKit install tool has correct schema"""
        from voice_mode.tools.livekit.install import livekit_install
        
        # Check tool metadata
        assert livekit_install.name == 'livekit_install'
        assert 'LiveKit' in livekit_install.description
        
        # Check parameters
        schema = livekit_install.schema
        properties = schema['properties']
        
        assert 'install_dir' in properties
        assert 'port' in properties
        assert 'force_reinstall' in properties
        assert 'auto_enable' in properties
        assert 'version' in properties
        
        # Check default values
        assert properties['port']['default'] == 7880
        assert properties['version']['default'] == 'latest'
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test infrastructure needs update for MCP API changes")
    async def test_livekit_frontend_tools_schema(self):
        """Test LiveKit frontend tools have correct schemas"""
        from voice_mode.tools.livekit.frontend import (
            livekit_frontend_start,
            livekit_frontend_stop,
            livekit_frontend_status
        )
        
        # Test start tool
        assert livekit_frontend_start.name == 'livekit_frontend_start'
        start_schema = livekit_frontend_start.schema
        assert 'port' in start_schema['properties']
        assert 'host' in start_schema['properties']
        assert start_schema['properties']['port']['default'] == 3000
        assert start_schema['properties']['host']['default'] == '127.0.0.1'
        
        # Test stop tool
        assert livekit_frontend_stop.name == 'livekit_frontend_stop'
        
        # Test status tool
        assert livekit_frontend_status.name == 'livekit_frontend_status'
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test infrastructure needs update for MCP API changes")
    async def test_service_tool_supports_livekit(self):
        """Test that the unified service tool supports LiveKit"""
        from voice_mode.tools.service import service
        
        # Test schema includes LiveKit
        schema = service.schema
        service_name_enum = schema['properties']['service_name']['enum']
        assert 'livekit' in service_name_enum
        
        # Test actions work with LiveKit
        action_enum = schema['properties']['action']['enum']
        expected_actions = [
            'status', 'start', 'stop', 'restart',
            'enable', 'disable', 'logs', 'update-service-files'
        ]
        for action in expected_actions:
            assert action in action_enum


class TestLiveKitProviderDiscovery:
    """Test cases for LiveKit provider discovery integration"""
    
    @pytest.mark.asyncio
    async def test_livekit_health_endpoint(self):
        """Test LiveKit health endpoint configuration"""
        from voice_mode import config
        
        # Check LiveKit configuration is available
        assert hasattr(config, 'LIVEKIT_PORT')
        assert hasattr(config, 'LIVEKIT_URL')
        assert hasattr(config, 'LIVEKIT_API_KEY')
        assert hasattr(config, 'LIVEKIT_API_SECRET')
        
        assert config.LIVEKIT_PORT == 7880
        assert config.LIVEKIT_URL == 'ws://localhost:7880'
        assert config.LIVEKIT_API_KEY == 'devkey'
        assert config.LIVEKIT_API_SECRET == 'secret'
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Test infrastructure needs update for service configuration API")
    async def test_livekit_in_service_config_vars(self):
        """Test LiveKit is included in service configuration variables"""
        from voice_mode.tools.service import get_service_config_vars
        
        config_vars = get_service_config_vars('livekit')
        
        # Check required config vars are present
        assert 'SERVICE_NAME' in config_vars
        assert config_vars['SERVICE_NAME'] == 'voicemode-livekit'
        
        assert 'LIVEKIT_BIN' in config_vars
        assert 'CONFIG_FILE' in config_vars
        assert 'WORKING_DIR' in config_vars
        
        # Check paths are correct
        assert config_vars['CONFIG_FILE'] == os.path.expanduser('~/.voicemode/config/livekit.yaml')


class TestLiveKitCLIIntegration:
    """Test cases for LiveKit CLI command integration"""
    
    def test_livekit_cli_group_exists(self):
        """Test LiveKit CLI group is properly registered"""
        from voice_mode.cli import voice_mode_main_cli
        
        # Get all command groups
        commands = voice_mode_main_cli.commands
        
        # Check LiveKit group exists
        assert 'livekit' in commands
        
        livekit_group = commands['livekit']
        assert livekit_group.name == 'livekit'
        
        # Check subcommands exist
        livekit_commands = livekit_group.commands
        expected_commands = [
            'status', 'start', 'stop', 'restart',
            'enable', 'disable', 'logs', 'update',
            'install', 'uninstall', 'frontend'
        ]
        
        for cmd in expected_commands:
            assert cmd in livekit_commands, f"Command '{cmd}' not found in LiveKit group"
    
    def test_livekit_frontend_subgroup_exists(self):
        """Test LiveKit frontend subgroup is properly registered"""
        from voice_mode.cli import voice_mode_main_cli
        
        livekit_group = voice_mode_main_cli.commands['livekit']
        frontend_group = livekit_group.commands['frontend']
        
        assert frontend_group.name == 'frontend'
        
        # Check frontend subcommands
        frontend_commands = frontend_group.commands
        expected_commands = ['start', 'stop', 'status']
        
        for cmd in expected_commands:
            assert cmd in frontend_commands, f"Frontend command '{cmd}' not found"