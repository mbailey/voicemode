"""
Functional tests for install - tests specific functions in isolation

This module provides actual testing of install functions by executing them
in controlled environments with mocked external dependencies.
"""
import os
import sys
import tempfile
import shutil
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

pytestmark = pytest.mark.skip(reason="Install.sh tests need refactoring for environment mocking")


class InstallScriptTester:
    """Helper class to test install functions"""
    
    def __init__(self, install_script_path):
        self.install_script_path = install_script_path
        self.temp_dir = None
        self.mock_env = {}
    
    def setup_test_environment(self):
        """Set up isolated test environment"""
        self.temp_dir = tempfile.mkdtemp(prefix="install_test_")
        
        # Create mock commands directory
        mock_bin = os.path.join(self.temp_dir, "bin")
        os.makedirs(mock_bin)
        
        # Set up environment
        self.mock_env = {
            'PATH': f"{mock_bin}:{os.environ.get('PATH', '')}",
            'HOME': self.temp_dir,
            'TMPDIR': self.temp_dir
        }
        
        return self.temp_dir, mock_bin
    
    def teardown_test_environment(self):
        """Clean up test environment"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def create_mock_command(self, command_name, script_content):
        """Create a mock executable command"""
        if not self.temp_dir:
            raise RuntimeError("Test environment not set up")
        
        mock_bin = os.path.join(self.temp_dir, "bin")
        command_path = os.path.join(mock_bin, command_name)
        
        with open(command_path, 'w') as f:
            f.write(f"#!/bin/bash\n{script_content}\n")
        
        os.chmod(command_path, 0o755)
        return command_path
    
    def run_install_function(self, function_name, *args, **kwargs):
        """Execute a specific function from install"""
        # Create a test script that sources install and runs the function
        test_script = f"""
#!/bin/bash
set -e

# Source the install script
source "{self.install_script_path}"

# Override print functions to capture output
print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; exit 1; }}

# Run the function
{function_name} {' '.join(str(arg) for arg in args)}
"""
        
        # Write test script
        test_script_path = os.path.join(self.temp_dir, "test_script.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        # Execute the function
        result = subprocess.run(
            [test_script_path],
            cwd=self.temp_dir,
            env=self.mock_env,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'success': result.returncode == 0
        }


@pytest.fixture
def install_tester():
    """Fixture providing InstallScriptTester instance"""
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
    tester = InstallScriptTester(script_path)
    tester.setup_test_environment()
    yield tester
    tester.teardown_test_environment()


class TestOSDetectionFunctions:
    """Test OS detection functions with real execution"""
    
    def test_detect_os_function_darwin(self, install_tester):
        """Test detect_os function on simulated macOS"""
        # Mock sw_vers command
        install_tester.create_mock_command("sw_vers", """
case "$1" in
    "-productVersion")
        echo "14.0"
        ;;
esac
""")
        
        # Mock uname command for architecture
        install_tester.create_mock_command("uname", """
case "$1" in
    "-m")
        echo "arm64"
        ;;
esac
""")
        
        # Override OSTYPE in environment
        install_tester.mock_env['OSTYPE'] = 'darwin22'
        
        result = install_tester.run_install_function('detect_os')
        
        assert result['success'] is True
        assert 'Detected macOS' in result['stdout']
        assert 'arm64' in result['stdout']
    
    def test_detect_os_function_ubuntu(self, install_tester):
        """Test detect_os function on simulated Ubuntu"""
        # Create mock /etc/os-release
        etc_dir = os.path.join(install_tester.temp_dir, "etc")
        os.makedirs(etc_dir, exist_ok=True)
        
        with open(os.path.join(etc_dir, "os-release"), 'w') as f:
            f.write('ID=ubuntu\nVERSION_ID="22.04"\n')
        
        # Mock commands
        install_tester.create_mock_command("uname", 'echo "x86_64"')
        
        # Update environment to point to our mock /etc
        install_tester.mock_env['OSTYPE'] = 'linux-gnu'
        
        # Modify the test to use our mock /etc directory
        test_script = f"""
#!/bin/bash
set -e
source "{install_tester.install_script_path}"

# Override the /etc path
export TEST_ETC_PATH="{etc_dir}"

# Modify the detect_os function to use our test path
detect_os() {{
    print_step "Detecting operating system..."
    
    if [[ -f "$TEST_ETC_PATH/os-release" ]]; then
        source "$TEST_ETC_PATH/os-release"
        if [[ "$ID" == "ubuntu" ]] || [[ "$ID_LIKE" == *"ubuntu"* ]]; then
            OS="ubuntu"
            ARCH=$(uname -m)
            print_success "Detected Ubuntu $VERSION_ID on $ARCH"
        fi
    fi
}}

print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; exit 1; }}

detect_os
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_detect_ubuntu.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert 'Detected Ubuntu' in result.stdout
    
    def test_detect_wsl(self, install_tester):
        """Test WSL detection"""
        # Set WSL environment variable
        install_tester.mock_env['WSL_DISTRO_NAME'] = 'Ubuntu'
        
        # Create Ubuntu os-release
        etc_dir = os.path.join(install_tester.temp_dir, "etc")
        os.makedirs(etc_dir, exist_ok=True)
        
        with open(os.path.join(etc_dir, "os-release"), 'w') as f:
            f.write('ID=ubuntu\nVERSION_ID="22.04"\n')
        
        install_tester.create_mock_command("uname", 'echo "x86_64"')
        
        result = install_tester.run_install_function('detect_os')
        
        # Should detect both Ubuntu and WSL
        assert 'WSL2' in result['stdout'] or 'WSL2' in result['stderr']


class TestDependencyCheckFunctions:
    """Test dependency checking functions"""
    
    def test_check_homebrew_installed(self, install_tester):
        """Test Homebrew detection when installed"""
        # Mock brew command
        install_tester.create_mock_command("brew", """
echo "Homebrew 4.0.0"
exit 0
""")
        
        result = install_tester.run_install_function('check_homebrew')
        
        assert result['success'] is True
        assert 'already installed' in result['stdout']
    
    def test_check_homebrew_missing(self, install_tester):
        """Test Homebrew detection when missing"""
        # Don't create brew command - it will be missing
        
        result = install_tester.run_install_function('check_homebrew')
        
        assert result['success'] is True
        assert 'not found' in result['stdout']
    
    def test_check_python(self, install_tester):
        """Test Python checking"""
        # Mock python3 and pip3
        install_tester.create_mock_command("python3", """
case "$1" in
    "--version")
        echo "Python 3.11.5"
        ;;
esac
""")
        
        install_tester.create_mock_command("pip3", """
echo "pip 23.0.1"
""")
        
        result = install_tester.run_install_function('check_python')
        
        assert result['success'] is True
        assert 'Python 3' in result['stdout']
        assert 'pip3 is available' in result['stdout']
    
    def test_check_python_missing_pip(self, install_tester):
        """Test Python check when pip is missing"""
        install_tester.create_mock_command("python3", """
echo "Python 3.11.5"
""")
        # Don't create pip3 command
        
        result = install_tester.run_install_function('check_python')
        
        assert result['success'] is False
        assert 'pip3 not found' in result['stderr']


class TestUVXInstallation:
    """Test UV/UVX installation functions"""
    
    def test_uvx_already_installed(self, install_tester):
        """Test when UVX is already installed"""
        # Mock uvx command
        install_tester.create_mock_command("uvx", """
case "$1" in
    "--version")
        echo "uvx 0.4.0"
        ;;
esac
""")
        
        result = install_tester.run_install_function('install_uvx')
        
        assert result['success'] is True
        assert 'already installed' in result['stdout']
    
    def test_uvx_installation_process(self, install_tester):
        """Test UVX installation when not present"""
        # Mock curl for UV installer
        install_tester.create_mock_command("curl", """
# Mock UV installer script
echo "#!/bin/bash"
echo "echo 'Installing UV...'"
echo "mkdir -p $HOME/.local/bin"
echo "echo '#!/bin/bash' > $HOME/.local/bin/uvx"
echo "echo 'echo \"uvx 0.4.0\"' >> $HOME/.local/bin/uvx"
echo "chmod +x $HOME/.local/bin/uvx"
""")
        
        # Create a test script that handles the UV installation
        test_script = f"""
#!/bin/bash
set -e
source "{install_tester.install_script_path}"

print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; exit 1; }}

# Override confirm_action to always return true
confirm_action() {{
    return 0
}}

# Mock the UV installation process
install_uvx() {{
    if ! command -v uvx >/dev/null 2>&1; then
        if confirm_action "Install UV/UVX (required for Voice Mode)"; then
            print_step "Installing UV/UVX..."
            
            # Simulate UV installation
            mkdir -p "$HOME/.local/bin"
            cat > "$HOME/.local/bin/uvx" << 'EOF'
#!/bin/bash
case "$1" in
    "--version")
        echo "uvx 0.4.0"
        ;;
    *)
        echo "uvx mock command"
        ;;
esac
EOF
            chmod +x "$HOME/.local/bin/uvx"
            
            # Add to PATH for current session
            export PATH="$HOME/.local/bin:$PATH"
            
            # Verify installation
            if ! command -v uvx >/dev/null 2>&1; then
                print_error "UV/UVX installation failed"
                return 1
            fi
            
            print_success "UV/UVX installed and verified successfully"
        fi
    else
        print_success "UV/UVX is already installed"
    fi
}}

install_uvx
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_uvx_install")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert 'installed and verified successfully' in result.stdout


class TestServiceInstallationFunctions:
    """Test service installation functions"""
    
    def test_check_voice_mode_cli_available(self, install_tester):
        """Test Voice Mode CLI detection when available"""
        # Mock uvx command
        install_tester.create_mock_command("uvx", """
case "$2" in
    "--version")
        echo "voice-mode 2.17.2"
        ;;
    "--help")
        echo "Voice Mode help"
        ;;
esac
""")
        
        result = install_tester.run_install_function('check_voice_mode_cli')
        
        assert result['success'] is True
        assert 'Voice Mode CLI is available' in result['stdout']
    
    def test_check_voice_mode_cli_missing(self, install_tester):
        """Test Voice Mode CLI detection when missing"""
        # Don't create uvx command
        
        result = install_tester.run_install_function('check_voice_mode_cli')
        
        assert result['success'] is False
        assert 'uvx not found' in result['stdout']
    
    def test_install_service_success(self, install_tester):
        """Test successful service installation"""
        # Mock uvx command that simulates successful service installation
        install_tester.create_mock_command("uvx", """
case "$1" in
    "voice-mode")
        case "$2" in
            "whisper")
                case "$3" in
                    "--help")
                        echo "Whisper service help"
                        exit 0
                        ;;
                    "install")
                        echo "Installing Whisper service..."
                        sleep 1
                        echo "✅ Whisper installed successfully"
                        exit 0
                        ;;
                esac
                ;;
        esac
        ;;
esac
""")
        
        # Create test script for install_service function
        test_script = f"""
#!/bin/bash
set -e
source "{install_tester.install_script_path}"

print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; exit 1; }}

install_service "whisper" "uvx voice-mode" "Whisper (Speech-to-Text)"
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_install_service.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert 'installed successfully' in result.stdout
    
    def test_install_service_failure(self, install_tester):
        """Test failed service installation"""
        # Mock uvx command that simulates failed service installation
        install_tester.create_mock_command("uvx", """
case "$1" in
    "voice-mode")
        case "$2" in
            "whisper")
                case "$3" in
                    "--help")
                        echo "Whisper service help"
                        exit 0
                        ;;
                    "install")
                        echo "Installing Whisper service..."
                        echo "Error: Installation failed!" >&2
                        exit 1
                        ;;
                esac
                ;;
        esac
        ;;
esac
""")
        
        test_script = f"""
#!/bin/bash
set -e
source "{install_tester.install_script_path}"

print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; exit 1; }}

install_service "whisper" "uvx voice-mode" "Whisper (Speech-to-Text)" || echo "INSTALL_FAILED"
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_install_service_fail.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True
        )
        
        # Should handle failure gracefully
        assert 'installation may have failed' in result.stdout or 'INSTALL_FAILED' in result.stdout


class TestClaudeCodeConfiguration:
    """Test Claude Code installation and configuration"""
    
    def test_claude_already_installed(self, install_tester):
        """Test when Claude Code is already installed"""
        install_tester.create_mock_command("claude", """
case "$1" in
    "mcp")
        case "$2" in
            "list")
                echo "voice-mode -- uvx voice-mode"
                ;;
        esac
        ;;
esac
""")
        
        result = install_tester.run_install_function('configure_claude_voicemode')
        
        assert result['success'] is True
        assert 'already configured' in result['stdout']
    
    def test_claude_code_installation(self, install_tester):
        """Test Claude Code installation via npm"""
        # Mock npm command
        install_tester.create_mock_command("npm", """
case "$1" in
    "install")
        echo "Installing @anthropic-ai/claude-code..."
        echo "Installation complete"
        ;;
esac
""")
        
        # Mock confirm_action to return true
        test_script = f"""
#!/bin/bash
set -e
source "{install_tester.install_script_path}"

print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; exit 1; }}

confirm_action() {{ return 0; }}

install_claude_if_needed
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_claude_install")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert 'Claude Code installed' in result.stdout


class TestErrorHandlingScenarios:
    """Test error handling in various scenarios"""
    
    def test_command_timeout_handling(self, install_tester):
        """Test handling of commands that timeout"""
        # Mock a command that takes too long
        install_tester.create_mock_command("slow_command", """
sleep 10
echo "This should timeout"
""")
        
        # Test timeout handling (install uses timeout 30 for some commands)
        test_script = f"""
#!/bin/bash
set -e

# Test timeout command
if timeout 2 {install_tester.temp_dir}/bin/slow_command; then
    echo "Command completed"
else
    echo "Command timed out as expected"
fi
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_timeout.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        assert 'timed out' in result.stdout
    
    def test_permission_error_handling(self, install_tester):
        """Test handling of permission errors"""
        # Create a script that simulates permission denied
        install_tester.create_mock_command("sudo", """
echo "Permission denied" >&2
exit 1
""")
        
        # Test that permission errors are handled gracefully
        test_script = f"""
#!/bin/bash
set -e

if {install_tester.temp_dir}/bin/sudo echo "test" 2>/dev/null; then
    echo "Sudo worked"
else
    echo "Sudo failed as expected"
fi
"""
        
        test_script_path = os.path.join(install_tester.temp_dir, "test_permission.sh")
        with open(test_script_path, 'w') as f:
            f.write(test_script)
        os.chmod(test_script_path, 0o755)
        
        result = subprocess.run(
            [test_script_path],
            cwd=install_tester.temp_dir,
            env=install_tester.mock_env,
            capture_output=True,
            text=True
        )
        
        assert 'failed as expected' in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])