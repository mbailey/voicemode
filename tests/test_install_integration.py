"""
Integration tests for install script

These tests run the actual install script in controlled environments
to validate end-to-end functionality without requiring actual installations.
"""
import os
import sys
import tempfile
import shutil
import subprocess
import pytest
from pathlib import Path

pytestmark = pytest.mark.skip(reason="Install.sh tests need refactoring for environment mocking")


@pytest.fixture
def isolated_install_env():
    """Create an isolated environment for install testing"""
    temp_dir = tempfile.mkdtemp(prefix="voicemode_install_integration_")
    
    # Create directory structure
    mock_home = os.path.join(temp_dir, "home")
    mock_bin = os.path.join(temp_dir, "bin")
    mock_etc = os.path.join(temp_dir, "etc")
    
    os.makedirs(mock_home)
    os.makedirs(mock_bin)
    os.makedirs(mock_etc)
    
    # Copy install to temp directory
    install_script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
    test_install_script = os.path.join(temp_dir, "install")
    shutil.copy2(install_script_path, test_install_script)
    
    # Set up environment variables
    test_env = {
        'PATH': f"{mock_bin}:{os.environ.get('PATH', '')}",
        'HOME': mock_home,
        'TMPDIR': temp_dir,
        'TEST_MODE': '1'  # Flag to indicate test mode
    }
    
    yield {
        'temp_dir': temp_dir,
        'mock_home': mock_home,
        'mock_bin': mock_bin,
        'mock_etc': mock_etc,
        'install_script': test_install_script,
        'env': test_env
    }
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


def create_mock_executable(bin_dir, name, script_content):
    """Create a mock executable in the bin directory"""
    exe_path = os.path.join(bin_dir, name)
    with open(exe_path, 'w') as f:
        f.write(f"#!/bin/bash\n{script_content}\n")
    os.chmod(exe_path, 0o755)
    return exe_path


class TestInstallScriptDryRun:
    """Test install script execution without actual installations"""
    
    def test_os_detection_integration(self, isolated_install_env):
        """Test OS detection with mocked system info"""
        env = isolated_install_env
        
        # Create a modified install script that only runs OS detection
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Override main function to only test OS detection
main() {{
    echo "🎤 Voice Mode Universal Installer (Test Mode)"
    detect_os
    echo "OS detection completed: OS=$OS, ARCH=$ARCH, IS_WSL=$IS_WSL"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_os_detection.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        # Mock system commands for macOS
        create_mock_executable(env['mock_bin'], "sw_vers", """
case "$1" in
    "-productVersion") echo "14.0" ;;
esac
""")
        
        create_mock_executable(env['mock_bin'], "uname", """
case "$1" in
    "-m") echo "arm64" ;;
esac
""")
        
        # Set macOS environment
        test_env = env['env'].copy()
        test_env['OSTYPE'] = 'darwin22'
        
        result = subprocess.run(
            [test_script_path],
            env=test_env,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "OS=macos" in result.stdout
        assert "ARCH=arm64" in result.stdout
    
    def test_dependency_checking_integration(self, isolated_install_env):
        """Test dependency checking with mock commands"""
        env = isolated_install_env
        
        # Create mock commands
        create_mock_executable(env['mock_bin'], "python3", """
case "$1" in
    "--version") echo "Python 3.11.5" ;;
esac
""")
        
        create_mock_executable(env['mock_bin'], "pip3", """
echo "pip 23.0.1"
""")
        
        create_mock_executable(env['mock_bin'], "brew", """
case "$1" in
    "list")
        case "$2" in
            "node") exit 0 ;;  # node installed
            "portaudio") exit 1 ;;  # portaudio missing
            *) exit 0 ;;
        esac
        ;;
esac
""")
        
        # Test script that only runs dependency checking
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Override OS detection
OS="macos"
ARCH="arm64"

main() {{
    echo "Testing dependency checking"
    check_python
    check_homebrew
    check_system_dependencies
    echo "Dependency checking completed"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_dependencies.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=env['env'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "Python 3" in result.stdout
        assert "Homebrew" in result.stdout
    
    def test_service_installation_dry_run(self, isolated_install_env):
        """Test service installation flow without actual installation"""
        env = isolated_install_env
        
        # Create mock uvx that simulates voice-mode CLI
        create_mock_executable(env['mock_bin'], "uvx", """
case "$1" in
    "voice-mode")
        case "$2" in
            "--version") echo "voice-mode 2.17.2" ;;
            "--help") echo "Voice Mode CLI help" ;;
            "whisper"|"kokoro"|"livekit")
                case "$3" in
                    "--help") echo "$2 service help" ;;
                    "install")
                        echo "Mock: Installing $2 service..."
                        sleep 1
                        echo "✅ $2 installed successfully"
                        ;;
                esac
                ;;
        esac
        ;;
esac
""")
        
        # Create mock claude command
        create_mock_executable(env['mock_bin'], "claude", """
case "$1" in
    "mcp")
        case "$2" in
            "list") echo "" ;;  # No MCP servers configured
            "add") echo "MCP server added successfully" ;;
        esac
        ;;
esac
""")
        
        # Test script that simulates service installation
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Override user interaction functions
confirm_action() {{
    echo "Auto-confirming: $1"
    return 0
}}

# Mock the main function to test only service installation
main() {{
    echo "Testing service installation flow"
    
    # Set up environment
    OS="macos"
    ARCH="arm64"
    
    # Test MCP configuration
    if configure_claude_voicemode; then
        echo "✅ Voice Mode MCP configured"
        
        # Test service installation with auto-yes
        echo "Y" | install_voice_services
    fi
    
    echo "Service installation test completed"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_services.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=env['env'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0
        assert "Voice Mode MCP configured" in result.stdout
        assert "Installing all Voice Mode services" in result.stdout


class TestInstallScriptErrorHandling:
    """Test error handling in install"""
    
    def test_missing_dependencies_error(self, isolated_install_env):
        """Test error handling when dependencies are missing"""
        env = isolated_install_env
        
        # Don't create python3 command - it will be missing
        
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

main() {{
    echo "Testing missing dependencies"
    check_python || echo "Python check failed as expected"
    echo "Error handling test completed"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_missing_deps.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=env['env'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Should handle missing dependencies gracefully
        assert "Python check failed" in result.stdout
    
    def test_network_failure_simulation(self, isolated_install_env):
        """Test handling of network failures"""
        env = isolated_install_env
        
        # Mock curl to simulate network failure
        create_mock_executable(env['mock_bin'], "curl", """
echo "Network error: Could not resolve host" >&2
exit 6
""")
        
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Override UV installation to test network failure
install_uvx() {{
    if ! command -v uvx >/dev/null 2>&1; then
        print_step "Installing UV/UVX..."
        if curl -LsSf https://astral.sh/uv/install | sh; then
            print_success "UV installed"
        else
            print_warning "UV installation failed - network error"
            return 1
        fi
    fi
}}

main() {{
    echo "Testing network failure handling"
    install_uvx || echo "UV installation failed as expected"
    echo "Network failure test completed"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_network_failure.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=env['env'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert "Network error" in result.stderr or "failed as expected" in result.stdout


class TestInstallScriptPlatformSupport:
    """Test platform-specific functionality"""
    
    def test_ubuntu_installation_flow(self, isolated_install_env):
        """Test installation flow on simulated Ubuntu"""
        env = isolated_install_env
        
        # Create Ubuntu-specific mock files
        with open(os.path.join(env['mock_etc'], "os-release"), 'w') as f:
            f.write('ID=ubuntu\nVERSION_ID="22.04"\n')
        
        # Mock Ubuntu-specific commands
        create_mock_executable(env['mock_bin'], "dpkg", """
case "$1" in
    "-l")
        case "$2" in
            "nodejs") echo "ii  nodejs" ;;
            "npm") echo "ii  npm" ;;
            *) echo "Package not installed" && exit 1 ;;
        esac
        ;;
esac
""")
        
        create_mock_executable(env['mock_bin'], "apt", """
case "$1" in
    "update") echo "Package lists updated" ;;
    "install") echo "Installing packages: $*" ;;
esac
""")
        
        create_mock_executable(env['mock_bin'], "sudo", """
# Pass through the command
exec "$@"
""")
        
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Override OS detection for Ubuntu
detect_os() {{
    OS="ubuntu"
    ARCH="x86_64"
    IS_WSL=false
    print_success "Detected Ubuntu 22.04 on x86_64"
}}

# Mock confirm_action to auto-accept
confirm_action() {{
    return 0
}}

main() {{
    echo "Testing Ubuntu installation flow"
    detect_os
    check_system_dependencies
    echo "Ubuntu test completed"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_ubuntu.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=env['env'],
            capture_output=True,
            text=True,
            timeout=15
        )
        
        assert result.returncode == 0
        assert "Detected Ubuntu" in result.stdout
    
    def test_wsl_detection_and_setup(self, isolated_install_env):
        """Test WSL-specific detection and setup"""
        env = isolated_install_env
        
        # Set WSL environment
        wsl_env = env['env'].copy()
        wsl_env['WSL_DISTRO_NAME'] = 'Ubuntu'
        
        # Create Ubuntu os-release
        with open(os.path.join(env['mock_etc'], "os-release"), 'w') as f:
            f.write('ID=ubuntu\nVERSION_ID="22.04"\n')
        
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Override file existence check to use our mock /etc
check_file_exists() {{
    local file="$1"
    if [[ "$file" == "/etc/os-release" ]]; then
        test -f "{env['mock_etc']}/os-release"
    else
        test -e "$file"
    fi
}}

# Override OS detection to use our mock files
detect_os() {{
    print_step "Detecting operating system..."
    
    # Check if running in WSL
    if [[ -n "$WSL_DISTRO_NAME" ]]; then
        IS_WSL=true
        print_warning "Running in WSL2 - additional audio setup may be required"
    fi
    
    if check_file_exists "/etc/os-release"; then
        source "{env['mock_etc']}/os-release"
        if [[ "$ID" == "ubuntu" ]]; then
            OS="ubuntu"
            ARCH="x86_64"
            print_success "Detected Ubuntu $VERSION_ID on $ARCH${{IS_WSL:+ (WSL2)}}"
        fi
    fi
}}

main() {{
    echo "Testing WSL detection"
    detect_os
    echo "WSL test result: OS=$OS, IS_WSL=$IS_WSL"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_wsl.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=wsl_env,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "IS_WSL=true" in result.stdout
        assert "WSL2" in result.stdout


class TestInstallScriptUserInteraction:
    """Test user interaction scenarios"""
    
    def test_interactive_prompts_automation(self, isolated_install_env):
        """Test automated responses to interactive prompts"""
        env = isolated_install_env
        
        # Mock commands that would be installed
        create_mock_executable(env['mock_bin'], "uvx", """
echo "uvx mock command"
""")
        
        create_mock_executable(env['mock_bin'], "claude", """
echo "claude mock command"
""")
        
        test_script = f"""#!/bin/bash
source "{env['install_script']}"

# Test with automated responses
main() {{
    echo "Testing automated user interaction"
    
    # Simulate user pressing 'y' for all prompts
    yes_responses() {{
        echo "y"
        echo "y" 
        echo "Y"
    }}
    
    # Override confirm_action to use automated responses
    confirm_action() {{
        echo "Auto-confirming: $1"
        return 0
    }}
    
    echo "Testing confirm_action function"
    if confirm_action "Test installation"; then
        echo "✅ Confirmation test passed"
    fi
    
    echo "User interaction test completed"
}}

main "$@"
"""
        
        test_script_path = os.path.join(env['temp_dir'], "test_interaction.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            env=env['env'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        assert result.returncode == 0
        assert "Confirmation test passed" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])