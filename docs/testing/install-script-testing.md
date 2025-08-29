# Install Script Testing Documentation

This document describes the comprehensive testing approach for the Voice Mode `install` script.

## Overview

The install script is a critical user-facing component that handles dependency installation, service setup, and system configuration. Robust testing is essential to catch regressions and ensure cross-platform compatibility.

## Testing Architecture

### 1. Unit Tests (`test_install_script_unit.py`)

**Purpose**: Test individual bash functions in isolation with comprehensive mocking.

**Key Features**:
- Extracts specific functions from install for isolated testing
- Mocks external commands and system dependencies
- Tests both success and failure scenarios
- Validates syntax and security patterns

**Example Test**:
```python
def test_detect_os_function_macos(self, install_script_path):
    """Test detect_os function for macOS detection"""
    function_code = self.extract_bash_function(install_script_path, "detect_os")
    
    # Mock system commands
    helper_functions = """
    sw_vers() { echo "14.0"; }
    uname() { echo "arm64"; }
    """
    
    result = self.run_bash_test(script)
    assert "RESULT_OS=macos" in result['stdout']
```

**Functions Tested**:
- `detect_os()` - OS detection for macOS, Ubuntu, Fedora, WSL
- `check_homebrew()` - Homebrew installation detection
- `check_python()` - Python and pip availability
- `confirm_action()` - User input handling
- `install_service()` - Service installation logic

### 2. Functional Tests (`test_install_functions.py`)

**Purpose**: Test install functions with more realistic execution environments.

**Key Features**:
- Creates isolated test environments with mock commands
- Tests function interaction and state management
- Validates cross-platform behavior
- Tests error handling and recovery

**Example Test**:
```python
def test_check_voice_mode_cli_available(self, install_tester):
    """Test Voice Mode CLI detection when available"""
    install_tester.create_mock_command("uvx", """
    case "$2" in
        "--version") echo "voice-mode 2.17.2" ;;
    esac
    """)
    
    result = install_tester.run_install_function('check_voice_mode_cli')
    assert 'Voice Mode CLI is available' in result['stdout']
```

### 3. Integration Tests (`test_install_integration.py`)

**Purpose**: Test complete installation flows end-to-end.

**Key Features**:
- Simulates full installation scenarios
- Tests user interaction flows
- Validates error handling in complex scenarios
- Cross-platform compatibility testing

**Note**: These tests create isolated environments but don't perform actual installations.

### 4. Validation Script (`test_install_services_fixed.sh`)

**Purpose**: Quick validation script for basic install functionality.

**Key Features**:
- Bash syntax validation
- Function existence checks
- Security pattern detection
- Basic loading tests

**Usage**:
```bash
./test_install_services_fixed.sh
```

## Running Tests

### Prerequisites

```bash
pip install pytest pytest-asyncio pytest-mock
```

### Running Unit Tests

```bash
# Run all unit tests
python -m pytest tests/test_install_script_unit.py -v

# Run specific test
python -m pytest tests/test_install_script_unit.py::TestInstallScriptFunctions::test_detect_os_function_macos -v

# Run with coverage
python -m pytest tests/test_install_script_unit.py --cov=. --cov-report=html
```

### Running Functional Tests

```bash
# Run all functional tests
python -m pytest tests/test_install_functions.py -v

# Run specific test category
python -m pytest tests/test_install_functions.py::TestOSDetectionFunctions -v
```

### Running Integration Tests

```bash
# Run integration tests (may take longer)
python -m pytest tests/test_install_integration.py -v
```

### Quick Validation

```bash
# Quick syntax and structure validation
./test_install_services_fixed.sh
```

## Test Coverage

### OS Detection
- ✅ macOS detection (Darwin)
- ✅ Ubuntu detection
- ✅ Fedora detection  
- ✅ WSL detection
- ✅ Unsupported OS handling

### Dependency Checking
- ✅ Homebrew detection (installed/missing)
- ✅ Python version checking
- ✅ pip availability
- ✅ System package verification
- ✅ UV/UVX installation

### Claude Code Integration
- ✅ Claude Code detection
- ✅ npm installation
- ✅ MCP configuration
- ✅ Voice Mode setup

### Service Installation
- ✅ Voice Mode CLI detection
- ✅ Service installation (whisper, kokoro, livekit)
- ✅ Installation success/failure handling
- ✅ User interaction (yes/no/selective)
- ✅ Timeout handling

### Error Scenarios
- ✅ Missing dependencies
- ✅ Network failures
- ✅ Permission errors
- ✅ Command timeouts
- ✅ Service installation failures

### Cross-Platform Support
- ✅ macOS (Homebrew, launchd)
- ✅ Ubuntu (apt, systemd)
- ✅ Fedora (dnf, systemd)
- ✅ WSL2 (audio setup)

## Known Issues and Limitations

### Current Issues
1. **TTY Redirection**: Line 8 in install (`exec </dev/tty`) causes issues in non-interactive environments
2. **External Dependencies**: Some tests require internet connectivity simulation
3. **Service Installation**: Full service testing requires complex mocking

### Testing Limitations
1. **No Actual Installations**: Tests mock all external commands
2. **Network Simulation**: Network errors are simulated, not real
3. **Platform Simulation**: OS detection uses mocked system info

### Recommendations for CI/CD
1. Run unit tests on every commit
2. Run integration tests on pull requests
3. Use different environments to test platform-specific code
4. Mock external services to avoid network dependencies

## Adding New Tests

### For New Functions
1. Add unit test in `test_install_script_unit.py`
2. Extract function using `extract_bash_function()`
3. Create appropriate mocks for dependencies
4. Test both success and failure scenarios

### For New Installation Flows
1. Add integration test in `test_install_integration.py`
2. Create isolated environment with required mocks
3. Test complete user interaction flow
4. Validate final state and error handling

### For New Platforms
1. Add OS detection test in unit tests
2. Add platform-specific integration test
3. Mock platform-specific commands and file systems
4. Test package manager and service manager differences

## Security Testing

### Patterns Checked
- No direct `eval $(curl ...)` commands
- No dangerous `rm -rf /` patterns
- No overly permissive `chmod 777`
- Proper input validation
- Safe temporary file handling

### Security Test Example
```python
def test_security_patterns(self):
    """Test for potential security issues"""
    with open(script_path, 'r') as f:
        content = f.read()
    
    unsafe_patterns = ['eval $(curl', 'rm -rf /', 'chmod 777']
    for pattern in unsafe_patterns:
        assert pattern not in content, f"Unsafe pattern: {pattern}"
```

## Best Practices

### Test Design
1. **Isolate Dependencies**: Mock all external commands and file systems
2. **Test Edge Cases**: Include error conditions and unexpected inputs
3. **Maintain Realism**: Mocks should behave like real commands
4. **Cross-Platform**: Test platform-specific code paths

### Mock Strategy
1. **Command Mocking**: Create executable scripts that simulate real commands
2. **File System Mocking**: Use temporary directories and mock file operations
3. **Environment Mocking**: Control environment variables and system info
4. **Network Mocking**: Simulate network conditions and failures

### Maintenance
1. **Keep Tests Updated**: Update tests when install changes
2. **Validate Coverage**: Ensure new code paths are tested
3. **Regular Execution**: Run tests frequently during development
4. **CI Integration**: Automate test execution in build pipeline

## Troubleshooting

### Common Test Failures

**"Function not found"**
- Check function name spelling
- Verify function exists in install
- Check function extraction logic

**"Command not found in test"**
- Ensure mock commands are created with correct names
- Verify PATH setup in test environment
- Check mock command permissions (should be executable)

**"Unexpected test behavior"**
- Review mock command logic
- Check environment variable setup
- Verify test isolation (no state leakage)

### Debugging Tests

```bash
# Run with verbose output
python -m pytest tests/test_install_script_unit.py -v -s

# Run single test with debugging
python -m pytest tests/test_install_script_unit.py::TestInstallScriptFunctions::test_detect_os_function_macos -v -s --tb=long

# Show print statements
python -m pytest tests/test_install_script_unit.py -s
```

This comprehensive testing approach ensures that the install script is robust, secure, and works correctly across different platforms and scenarios.