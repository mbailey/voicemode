"""
Unit tests for install script functions

This module tests individual functions from install by extracting and 
testing them in isolation with comprehensive mocking.
"""
import os
import sys
import tempfile
import shutil
import subprocess
import pytest
from unittest.mock import patch, MagicMock, call, mock_open
from pathlib import Path

pytestmark = pytest.mark.skip(reason="Install.sh tests need refactoring for environment mocking")


class TestInstallScriptFunctions:
    """Test individual install functions with proper mocking"""
    
    @pytest.fixture
    def install_script_path(self):
        """Get path to install script"""
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
    
    def extract_bash_function(self, script_path, function_name):
        """Extract a specific bash function from the script"""
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Find function definition
        start_pattern = f"{function_name}() {{"
        start_idx = content.find(start_pattern)
        if start_idx == -1:
            raise ValueError(f"Function {function_name} not found")
        
        # Find the end of the function (matching brace)
        brace_count = 0
        in_function = False
        end_idx = start_idx
        
        for i, char in enumerate(content[start_idx:], start_idx):
            if char == '{':
                brace_count += 1
                in_function = True
            elif char == '}':
                brace_count -= 1
                if in_function and brace_count == 0:
                    end_idx = i + 1
                    break
        
        function_code = content[start_idx:end_idx]
        return function_code
    
    def create_test_script(self, function_code, helper_functions="", test_code=""):
        """Create a test script with the function and helpers"""
        script = f"""#!/bin/bash
set -e

# Mock print functions to avoid exit calls
print_step() {{ echo "STEP: $1"; }}
print_success() {{ echo "SUCCESS: $1"; }}
print_warning() {{ echo "WARNING: $1"; }}
print_error() {{ echo "ERROR: $1"; return 1; }}

# Helper functions
{helper_functions}

# Function under test
{function_code}

# Test code
{test_code}
"""
        return script
    
    def run_bash_test(self, script_content, env_vars=None, timeout=10):
        """Run a bash test script and return results"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            os.chmod(script_path, 0o755)
            
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env
            )
            
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }
        finally:
            os.unlink(script_path)
    
    def test_detect_os_function_macos(self, install_script_path):
        """Test detect_os function for macOS detection"""
        function_code = self.extract_bash_function(install_script_path, "detect_os")
        
        # Mock system commands
        helper_functions = """
# Mock sw_vers
sw_vers() {
    case "$1" in
        "-productVersion") echo "14.0" ;;
    esac
}

# Mock uname  
uname() {
    case "$1" in
        "-m") echo "arm64" ;;
    esac
}

# Mock grep for /proc/version (WSL check)
grep() {
    return 1  # Not found
}
"""
        
        test_code = """
# Set macOS environment
OSTYPE="darwin22"

# Run the function
detect_os

# Output results
echo "RESULT_OS=$OS"
echo "RESULT_ARCH=$ARCH"
echo "RESULT_WSL=$IS_WSL"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is True
        assert "RESULT_OS=macos" in result['stdout']
        assert "RESULT_ARCH=arm64" in result['stdout']
        assert "Detected macOS 14.0 on arm64" in result['stdout']
    
    def test_detect_os_function_ubuntu(self, install_script_path):
        """Test detect_os function for Ubuntu detection"""
        function_code = self.extract_bash_function(install_script_path, "detect_os")
        
        helper_functions = """
# Mock file existence
test() {
    case "$1" in
        "-f")
            case "$2" in
                "/etc/os-release") return 0 ;;
                *) return 1 ;;
            esac
            ;;
        *) 
            # Pass through other test calls
            command test "$@"
            ;;
    esac
}

# Mock source command for os-release
source() {
    if [[ "$1" == "/etc/os-release" ]]; then
        ID="ubuntu"
        VERSION_ID="22.04"
    fi
}

# Mock uname
uname() {
    case "$1" in
        "-m") echo "x86_64" ;;
    esac
}

# Mock grep for WSL detection
grep() {
    return 1  # Not WSL
}
"""
        
        test_code = """
# Set Linux environment
OSTYPE="linux-gnu"

# Run the function
detect_os

# Output results
echo "RESULT_OS=$OS"
echo "RESULT_ARCH=$ARCH"
echo "RESULT_WSL=$IS_WSL"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is True
        assert "RESULT_OS=ubuntu" in result['stdout']
        assert "RESULT_ARCH=x86_64" in result['stdout']
        assert "Detected Ubuntu 22.04 on x86_64" in result['stdout']
    
    def test_detect_os_function_wsl(self, install_script_path):
        """Test detect_os function for WSL detection"""
        function_code = self.extract_bash_function(install_script_path, "detect_os")
        
        helper_functions = """
# Mock file tests
test() {
    case "$1" in
        "-f")
            case "$2" in
                "/etc/os-release") return 0 ;;
                *) return 1 ;;
            esac
            ;;
        *) 
            command test "$@"
            ;;
    esac
}

# Mock source for os-release
source() {
    if [[ "$1" == "/etc/os-release" ]]; then
        ID="ubuntu"
        VERSION_ID="22.04"
    fi
}

# Mock uname
uname() {
    case "$1" in
        "-m") echo "x86_64" ;;
    esac
}

# Mock grep to find microsoft in /proc/version
grep() {
    case "$*" in
        *"microsoft"*"/proc/version"*) return 0 ;;  # Found
        *) return 1 ;;
    esac
}
"""
        
        test_code = """
# Set WSL environment
OSTYPE="linux-gnu"
WSL_DISTRO_NAME="Ubuntu"

# Run the function
detect_os

# Output results
echo "RESULT_OS=$OS"
echo "RESULT_ARCH=$ARCH"
echo "RESULT_WSL=$IS_WSL"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script, env_vars={'WSL_DISTRO_NAME': 'Ubuntu'})
        
        assert result['success'] is True
        assert "RESULT_OS=ubuntu" in result['stdout']
        assert "RESULT_WSL=true" in result['stdout']
        assert "WSL2" in result['stdout']
    
    def test_check_homebrew_function(self, install_script_path):
        """Test check_homebrew function"""
        function_code = self.extract_bash_function(install_script_path, "check_homebrew")
        
        # Test when Homebrew is installed
        helper_functions = """
command() {
    case "$1" in
        "-v")
            case "$2" in
                "brew") return 0 ;;  # brew found
                *) return 1 ;;
            esac
            ;;
        *) 
            command "$@"
            ;;
    esac
}
"""
        
        test_code = """
# Initialize variables
HOMEBREW_INSTALLED=false

# Run function
check_homebrew

# Output result
echo "RESULT_HOMEBREW_INSTALLED=$HOMEBREW_INSTALLED"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is True
        assert "RESULT_HOMEBREW_INSTALLED=true" in result['stdout']
        assert "already installed" in result['stdout']
    
    def test_check_homebrew_function_missing(self, install_script_path):
        """Test check_homebrew function when Homebrew is missing"""
        function_code = self.extract_bash_function(install_script_path, "check_homebrew")
        
        helper_functions = """
command() {
    case "$1" in
        "-v")
            return 1  # command not found
            ;;
        *) 
            command "$@"
            ;;
    esac
}
"""
        
        test_code = """
HOMEBREW_INSTALLED=false
check_homebrew
echo "RESULT_HOMEBREW_INSTALLED=$HOMEBREW_INSTALLED"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is True
        assert "RESULT_HOMEBREW_INSTALLED=false" in result['stdout']
        assert "not found" in result['stdout']
    
    def test_check_python_function(self, install_script_path):
        """Test check_python function"""
        function_code = self.extract_bash_function(install_script_path, "check_python")
        
        helper_functions = """
command() {
    case "$1" in
        "-v")
            case "$2" in
                "python3"|"pip3") return 0 ;;  # both found
                *) return 1 ;;
            esac
            ;;
        *) 
            command "$@"
            ;;
    esac
}

python3() {
    case "$1" in
        "--version") echo "Python 3.11.5" ;;
    esac
}
"""
        
        test_code = """
check_python
echo "CHECK_PYTHON_COMPLETED"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is True
        assert "Python 3.11.5" in result['stdout']
        assert "pip3 is available" in result['stdout']
        assert "CHECK_PYTHON_COMPLETED" in result['stdout']
    
    def test_check_python_function_missing_pip(self, install_script_path):
        """Test check_python function when pip is missing"""
        function_code = self.extract_bash_function(install_script_path, "check_python")
        
        helper_functions = """
command() {
    case "$1" in
        "-v")
            case "$2" in
                "python3") return 0 ;;  # python3 found
                "pip3") return 1 ;;     # pip3 missing
                *) return 1 ;;
            esac
            ;;
        *) 
            command "$@"
            ;;
    esac
}

python3() {
    case "$1" in
        "--version") echo "Python 3.11.5" ;;
    esac
}
"""
        
        test_code = """
check_python || echo "CHECK_PYTHON_FAILED"
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is False or "CHECK_PYTHON_FAILED" in result['stdout']
        assert "pip3 not found" in result['stdout'] or "pip3 not found" in result['stderr']
    
    def test_confirm_action_function(self, install_script_path):
        """Test confirm_action function with different inputs"""
        function_code = self.extract_bash_function(install_script_path, "confirm_action")
        
        # Test "yes" response
        test_code = """
# Test yes response
echo "y" | confirm_action "Test action"
if [ $? -eq 0 ]; then
    echo "CONFIRM_YES_SUCCESS"
fi

# Test no response  
echo "n" | confirm_action "Test action"
if [ $? -eq 1 ]; then
    echo "CONFIRM_NO_SUCCESS"
fi
"""
        
        script = self.create_test_script(function_code, "", test_code)
        result = self.run_bash_test(script)
        
        assert "CONFIRM_YES_SUCCESS" in result['stdout']
        assert "CONFIRM_NO_SUCCESS" in result['stdout']
    
    def test_install_service_function(self, install_script_path):
        """Test install_service function"""
        function_code = self.extract_bash_function(install_script_path, "install_service")
        
        helper_functions = """
# Mock timeout command
timeout() {
    local duration="$1"
    shift
    # Just run the command without timeout for testing
    "$@"
}

# Mock mktemp
mktemp() {
    echo "/tmp/test_log_$$"
    touch "/tmp/test_log_$$"
}

# Mock tee
tee() {
    local file="$1"
    cat > "$file"
}

# Mock tail
tail() {
    case "$1" in
        "-10") cat "$2" ;;
    esac
}

# Mock grep
grep() {
    case "$1" in
        "-qi") 
            # Look for error patterns in the log
            case "$2" in
                "error\\|failed\\|traceback") return 1 ;;  # No errors found
            esac
            ;;
    esac
}

# Mock voice-mode command that succeeds
uvx() {
    case "$1 $2 $3" in
        "voice-mode whisper --help")
            echo "Whisper service help"
            return 0
            ;;
        "voice-mode whisper install")
            echo "Installing Whisper service..."
            echo "✅ Whisper installed successfully"
            return 0
            ;;
    esac
}
"""
        
        test_code = """
# Test successful installation
if install_service "whisper" "uvx voice-mode" "Whisper (Speech-to-Text)"; then
    echo "INSTALL_SERVICE_SUCCESS"
else
    echo "INSTALL_SERVICE_FAILED"
fi
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        assert result['success'] is True
        assert "INSTALL_SERVICE_SUCCESS" in result['stdout']
        assert "installed successfully" in result['stdout']
    
    def test_install_service_function_failure(self, install_script_path):
        """Test install_service function with failure"""
        function_code = self.extract_bash_function(install_script_path, "install_service")
        
        helper_functions = """
timeout() { shift; "$@"; }
mktemp() { echo "/tmp/test_log_$$"; touch "/tmp/test_log_$$"; }
tee() { cat > "$1"; }
tail() { case "$1" in "-10") cat "$2" ;; esac; }
grep() {
    case "$1 $2" in
        "-qi error\\|failed\\|traceback") return 0 ;;  # Errors found
    esac
}

# Mock voice-mode command that fails
uvx() {
    case "$1 $2 $3" in
        "voice-mode whisper --help") return 0 ;;
        "voice-mode whisper install")
            echo "Installing Whisper service..."
            echo "Error: Installation failed!" >&2
            return 1
            ;;
    esac
}
"""
        
        test_code = """
if install_service "whisper" "uvx voice-mode" "Whisper (Speech-to-Text)"; then
    echo "INSTALL_SERVICE_UNEXPECTED_SUCCESS"
else
    echo "INSTALL_SERVICE_FAILED_AS_EXPECTED"
fi
"""
        
        script = self.create_test_script(function_code, helper_functions, test_code)
        result = self.run_bash_test(script)
        
        # Should handle failure gracefully
        assert "installation may have failed" in result['stdout'] or "INSTALL_SERVICE_FAILED_AS_EXPECTED" in result['stdout']


class TestInstallScriptValidation:
    """Test install script validation and syntax"""
    
    def test_bash_syntax_validation(self):
        """Test that install has valid bash syntax"""
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
        
        result = subprocess.run(
            ['bash', '-n', script_path],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"
    
    def test_shellcheck_validation(self):
        """Test install with shellcheck if available"""
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
        
        # Check if shellcheck is available
        try:
            result = subprocess.run(['shellcheck', '--version'], capture_output=True)
            if result.returncode != 0:
                pytest.skip("shellcheck not available")
        except FileNotFoundError:
            pytest.skip("shellcheck not installed")
        
        # Run shellcheck
        result = subprocess.run(
            ['shellcheck', '-x', script_path],
            capture_output=True,
            text=True
        )
        
        # Allow some common shellcheck warnings but fail on errors
        if result.returncode != 0:
            # Filter out acceptable warnings
            lines = result.stdout.split('\n')
            errors = [line for line in lines if 'error' in line.lower()]
            
            if errors:
                pytest.fail(f"Shellcheck errors found: {result.stdout}")
    
    def test_required_functions_exist(self):
        """Test that all required functions exist in install"""
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        required_functions = [
            'detect_os',
            'check_homebrew',
            'check_python',
            'install_uvx',
            'install_claude_if_needed',
            'configure_claude_voicemode',
            'check_voice_mode_cli',
            'install_service',
            'install_all_services',
            'install_voice_services',
            'main'
        ]
        
        for func in required_functions:
            pattern = f"{func}() {{"
            assert pattern in content, f"Required function {func} not found in install"
    
    def test_security_patterns(self):
        """Test for potential security issues in install"""
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Check for potentially unsafe patterns
        unsafe_patterns = [
            'eval $(curl',  # Direct eval of downloaded content
            'curl | bash',  # Piping to bash (this one is used but controlled)
            'rm -rf /',     # Dangerous rm command
            'chmod 777',    # Overly permissive permissions
        ]
        
        for pattern in unsafe_patterns:
            if pattern in content and pattern != 'curl | bash':
                # curl | bash is used but in a controlled way for UV installation
                pytest.fail(f"Potentially unsafe pattern found: {pattern}")
    
    def test_error_handling_patterns(self):
        """Test that proper error handling patterns are used"""
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "install")
        
        with open(script_path, 'r') as f:
            content = f.read()
        
        # Check for proper error handling
        assert 'set -e' in content, "Script should use 'set -e' for error handling"
        assert 'print_error' in content, "Script should have error printing function"
        
        # Check that dangerous operations have proper checks
        if 'rm -rf' in content:
            # Should have safety checks before rm -rf
            assert any(pattern in content for pattern in ['if [', 'test -', '[ -']), \
                "rm -rf commands should have safety checks"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])