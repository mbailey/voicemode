#!/bin/bash
# Fixed test script for install service installation feature
# This script provides basic validation that install functions work

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_test() {
    echo -e "${BLUE}TEST: $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_failure() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SCRIPT="$SCRIPT_DIR/install"

# Test counter
TESTS_RUN=0
TESTS_PASSED=0

run_test() {
    local test_name="$1"
    local test_command="$2"
    
    print_test "$test_name"
    TESTS_RUN=$((TESTS_RUN + 1))
    
    if eval "$test_command"; then
        print_success "$test_name passed"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        print_failure "$test_name failed"
    fi
    echo ""
}

# Test 1: Basic syntax validation
test_syntax() {
    bash -n "$INSTALL_SCRIPT"
}

# Test 2: Check required functions exist
test_functions_exist() {
    local functions=(
        "detect_os"
        "check_homebrew" 
        "check_python"
        "install_uvx"
        "configure_claude_voicemode"
        "check_voice_mode_cli"
        "install_service"
        "install_all_services"
        "main"
    )
    
    for func in "${functions[@]}"; do
        if ! grep -q "^${func}()" "$INSTALL_SCRIPT"; then
            echo "Function $func not found"
            return 1
        fi
    done
    
    return 0
}

# Test 3: Check for security patterns
test_security() {
    # Check for potentially dangerous patterns
    local dangerous_patterns=(
        "eval \$(curl"
        "rm -rf /"
        "chmod 777"
    )
    
    for pattern in "${dangerous_patterns[@]}"; do
        if grep -q "$pattern" "$INSTALL_SCRIPT"; then
            echo "Dangerous pattern found: $pattern"
            return 1
        fi
    done
    
    return 0
}

# Test 4: Test help/dry-run mode doesn't break
test_help_mode() {
    # Try to source the script and check basic function availability
    # This tests that the script can be loaded without executing main
    
    local temp_script=$(mktemp)
    cat > "$temp_script" << 'EOF'
#!/bin/bash
set -e

# Mock print functions to avoid exits
print_step() { echo "STEP: $1"; }
print_success() { echo "SUCCESS: $1"; }
print_warning() { echo "WARNING: $1"; }
print_error() { echo "ERROR: $1"; return 1; }

# Source the install script but don't run main
source "$1"

# Test that key functions are available
if declare -f detect_os >/dev/null && \
   declare -f check_homebrew >/dev/null && \
   declare -f install_service >/dev/null; then
    echo "Key functions available"
    exit 0
else
    echo "Key functions missing"
    exit 1
fi
EOF
    
    chmod +x "$temp_script"
    "$temp_script" "$INSTALL_SCRIPT"
    local result=$?
    rm -f "$temp_script"
    
    return $result
}

# Test 5: Validate error handling
test_error_handling() {
    # Check that script uses proper error handling
    grep -q "set -e" "$INSTALL_SCRIPT" && \
    grep -q "print_error" "$INSTALL_SCRIPT"
}

# Main test runner
main() {
    echo -e "${BLUE}🧪 Voice Mode install Basic Validation Tests${NC}"
    echo "============================================="
    echo ""
    
    if [[ ! -f "$INSTALL_SCRIPT" ]]; then
        print_failure "install not found at $INSTALL_SCRIPT"
        exit 1
    fi
    
    print_info "Testing install at: $INSTALL_SCRIPT"
    echo ""
    
    # Run tests
    run_test "Bash syntax validation" "test_syntax"
    run_test "Required functions exist" "test_functions_exist"
    run_test "Security pattern check" "test_security"
    run_test "Script loading test" "test_help_mode"
    run_test "Error handling validation" "test_error_handling"
    
    # Summary
    echo "============================================="
    echo -e "${BLUE}Test Summary:${NC}"
    echo "Tests run: $TESTS_RUN"
    echo "Tests passed: $TESTS_PASSED"
    echo "Tests failed: $((TESTS_RUN - TESTS_PASSED))"
    
    if [[ $TESTS_PASSED -eq $TESTS_RUN ]]; then
        echo ""
        print_success "All tests passed! install appears to be working correctly."
        echo ""
        print_info "For comprehensive testing, run:"
        echo "  python -m pytest tests/test_install_script_unit.py -v"
        echo "  python -m pytest tests/test_install_functions.py -v"
        exit 0
    else
        echo ""
        print_failure "Some tests failed. Please check the issues above."
        exit 1
    fi
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi