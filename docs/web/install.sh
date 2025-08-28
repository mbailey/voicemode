#!/bin/bash
# VoiceMode Universal Installer
# Usage: curl -sSf https://getvoicemode.com/install.sh | sh

# set -e

# Parse command line arguments
show_help() {
  cat <<EOF
VoiceMode Universal Installer

Usage: $0 [OPTIONS]

Options:
  -h, --help     Show this help message
  -d, --debug    Enable debug output
  
Environment variables:
  VOICEMODE_INSTALL_DEBUG=true    Enable debug output
  DEBUG=true                      Enable debug output

Examples:
  # Normal installation
  curl -O https://getvoicemode.com/install.sh && bash install.sh
  
  # Debug mode
  VOICEMODE_INSTALL_DEBUG=true ./install.sh
  ./install.sh --debug
  
EOF
  exit 0
}

# Process arguments
while [[ $# -gt 0 ]]; do
  case $1 in
  -h | --help)
    show_help
    ;;
  -d | --debug)
    export VOICEMODE_INSTALL_DEBUG=true
    shift
    ;;
  --test-error)
    export VOICEMODE_TEST_ERROR=true
    shift
    ;;
  *)
    echo "Unknown option: $1"
    echo "Use --help for usage information"
    exit 1
    ;;
  esac
done

# Support DEBUG=true as well as VOICEMODE_INSTALL_DEBUG=true
if [[ "${DEBUG:-}" == "true" ]]; then
  export VOICEMODE_INSTALL_DEBUG=true
fi

# Reattach stdin to terminal for interactive prompts when run via curl | bash
[ -t 0 ] || exec </dev/tty # reattach keyboard to STDIN

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
ORANGE='\033[38;5;208m' # Claude Code orange
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Global variables
OS=""
ARCH=""
HOMEBREW_INSTALLED=false
XCODE_TOOLS_INSTALLED=false
IS_WSL=false

# Logging configuration
VOICEMODE_DATA_DIR="${HOME}/.voicemode"
LOG_DIR="${VOICEMODE_DATA_DIR}/logs"
LOG_FILE=""
AUTO_SUBMIT=false
SUBMISSION_ENDPOINT="https://api.voicemode.io/v1/install-reports" # Mock endpoint for now

# Initialize logging
init_logging() {
  mkdir -p "$LOG_DIR"
  LOG_FILE="${LOG_DIR}/install-$(date +%Y%m%d-%H%M%S).log"
  
  # Check for auto-submit preference
  if [[ -f "${VOICEMODE_DATA_DIR}/.submit-logs" ]]; then
    AUTO_SUBMIT=true
  fi
  
  # Write initial log entry
  log_info "VoiceMode Installation started at $(date)"
  log_info "OS: $(uname -s)"
  log_info "Kernel: $(uname -r)"
  log_info "Architecture: $(uname -m)"
  log_info "Shell: ${SHELL}"
  log_info "User: [USER]" # Pre-sanitized
  log_info "Home: [HOME]" # Pre-sanitized
}

# Logging functions
log_message() {
  local level="$1"
  shift
  local message="$*"
  local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  
  # Write to log file if it exists
  if [[ -n "$LOG_FILE" ]]; then
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
  fi
  
  # Also output based on level (but don't duplicate print_* functions)
  case "$level" in
    DEBUG)
      [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]] && echo -e "${DIM}[DEBUG] $message${NC}" >&2
      ;;
  esac
}

log_error() { log_message "ERROR" "$@"; }
log_warn()  { log_message "WARN" "$@"; }
log_info()  { log_message "INFO" "$@"; }
log_debug() { log_message "DEBUG" "$@"; }

# Sanitize log content to remove PII
sanitize_log() {
  local content="$1"
  local username="${USER:-$(whoami)}"
  
  # Remove username from paths
  content="${content//$username/\[USER\]}"
  content="${content//$HOME/\[HOME\]}"
  
  # Remove IP addresses
  content=$(echo "$content" | sed -E 's/[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[IP]/g')
  
  # Remove email addresses
  content=$(echo "$content" | sed -E 's/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/[EMAIL]/g')
  
  # Remove API keys/tokens (common patterns)
  content=$(echo "$content" | sed -E 's/(api[_-]?key|token|secret|password)[[:space:]]*[:=][[:space:]]*[^[:space:]]+/\1=[REDACTED]/gi')
  
  echo "$content"
}

# Generate JSON error report
generate_json_report() {
  local exit_code="${1:-1}"
  local failed_step="${2:-unknown}"
  local error_message="${3:-Installation failed}"
  
  cat <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "os": "$(uname -s)",
  "os_version": "$(uname -r)",
  "arch": "$(uname -m)",
  "shell": "${SHELL##*/}",
  "python_version": "$(python3 --version 2>&1 | cut -d' ' -f2 || echo 'not installed')",
  "node_version": "$(node --version 2>&1 || echo 'not installed')",
  "exit_code": $exit_code,
  "failed_step": "$failed_step",
  "error_message": "$error_message",
  "is_wsl": $IS_WSL
}
EOF
}

# Prompt user for error submission
prompt_error_submission() {
  local exit_code="${1:-1}"
  local failed_step="${2:-unknown}"
  local error_message="${3:-Installation failed}"
  local report_file="${LOG_FILE}.json"
  
  echo ""
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  echo -e "${YELLOW} Installation encountered an error${NC}"
  echo -e "${YELLOW}═══════════════════════════════════════════════════════${NC}"
  echo ""
  echo "Would you like to submit an error report to help improve VoiceMode?"
  echo "The report contains only technical information (no personal data)."
  echo ""
  echo "Options:"
  echo "  [y]es     - Submit this report"
  echo "  [a]lways  - Always submit reports automatically"
  echo "  [v]iew    - View the report first"
  echo "  [n]o      - Don't submit (default)"
  echo ""
  
  local choice
  read -p "Your choice [y/a/v/N]: " choice
  
  case "${choice,,}" in
    y|yes)
      submit_error_report "$exit_code" "$failed_step" "$error_message"
      ;;
    a|always)
      touch "${VOICEMODE_DATA_DIR}/.submit-logs"
      echo -e "${GREEN}Auto-submission enabled. You can disable this by removing:${NC}"
      echo -e "${GREEN}  ${VOICEMODE_DATA_DIR}/.submit-logs${NC}"
      submit_error_report "$exit_code" "$failed_step" "$error_message"
      ;;
    v|view)
      view_and_prompt_report "$exit_code" "$failed_step" "$error_message"
      ;;
    *)
      echo "Report not submitted. Log saved at: $LOG_FILE"
      ;;
  esac
}

# View report and prompt again
view_and_prompt_report() {
  local exit_code="${1:-1}"
  local failed_step="${2:-unknown}"
  local error_message="${3:-Installation failed}"
  local report_file="${LOG_FILE}.json"
  generate_json_report "$exit_code" "$failed_step" "$error_message" > "$report_file"
  
  # Sanitize the report
  local sanitized=$(sanitize_log "$(cat "$report_file")")
  echo "$sanitized" > "$report_file"
  
  # Show in pager
  ${PAGER:-less} "$report_file"
  
  echo ""
  echo "After viewing the report, would you like to submit it?"
  local choice
  read -p "[y]es / [n]o / [a]lways: " choice
  
  case "${choice,,}" in
    y|yes)
      submit_error_report "$exit_code" "$failed_step" "$error_message"
      ;;
    a|always)
      touch "${VOICEMODE_DATA_DIR}/.submit-logs"
      submit_error_report "$exit_code" "$failed_step" "$error_message"
      ;;
    *)
      echo "Report not submitted."
      ;;
  esac
}

# Submit error report (mock for now)
submit_error_report() {
  local exit_code="${1:-1}"
  local failed_step="${2:-unknown}"
  local error_message="${3:-Installation failed}"
  local report_file="${LOG_FILE}.json"
  
  # Generate and sanitize report
  generate_json_report "$exit_code" "$failed_step" "$error_message" > "$report_file"
  local sanitized=$(sanitize_log "$(cat "$report_file")")
  echo "$sanitized" > "$report_file"
  
  # Mock submission for now (will be replaced with actual endpoint)
  echo -e "${GREEN}Report prepared for submission (mock mode - not actually sent)${NC}"
  echo -e "${DIM}Report saved at: $report_file${NC}"
  
  # When ready for production, uncomment:
  # local response=$(curl -s -X POST \
  #   -H "Content-Type: application/json" \
  #   -d "@$report_file" \
  #   "$SUBMISSION_ENDPOINT" \
  #   2>/dev/null || echo '{"error":"submission_failed"}')
  # 
  # if [[ "$response" == *"success"* ]]; then
  #   echo -e "${GREEN}Report submitted successfully. Thank you!${NC}"
  # else
  #   echo -e "${YELLOW}Report submission failed. Log saved at: $report_file${NC}"
  # fi
}

# Error handler
handle_installation_error() {
  local exit_code=$?
  local line_number="${BASH_LINENO[0]}"
  local failed_command="${1:-unknown}"
  
  log_error "Installation failed at line $line_number"
  log_error "Failed command: $failed_command"
  log_error "Exit code: $exit_code"
  
  # Try to determine which step failed based on the command
  local failed_step="unknown"
  case "$failed_command" in
    *detect_os*)
      failed_step="os_detection"
      ;;
    *install_prerequisites*)
      failed_step="prerequisites"
      ;;
    *install_uv*)
      failed_step="uv_installation"
      ;;
    *install_voicemode*)
      failed_step="voicemode_installation"
      ;;
    *configure_claude*)
      failed_step="claude_configuration"
      ;;
    *)
      failed_step="command: ${failed_command:0:50}"
      ;;
  esac
  
  # Generate error report
  if [[ "$AUTO_SUBMIT" == "true" ]]; then
    echo -e "${YELLOW}Auto-submitting error report...${NC}"
    submit_error_report "$exit_code" "$failed_step" "$failed_command"
  else
    prompt_error_submission "$exit_code" "$failed_step" "$failed_command"
  fi
  
  exit $exit_code
}

print_step() {
  echo -e "${BLUE}🔧 $1${NC}"
  log_info "STEP: $1"
}

print_success() {
  echo -e "${GREEN}✅ $1${NC}"
  log_info "SUCCESS: $1"
}

print_warning() {
  echo -e "${YELLOW}⚠️  $1${NC}"
  log_warn "WARNING: $1"
}

print_error() {
  echo -e "${RED}❌ $1${NC}"
  log_error "ERROR: $1"
  exit 1
}

detect_os() {
  print_step "Detecting operating system..."

  # Check if running in WSL
  # More robust WSL detection to avoid false positives
  if [[ -n "$WSL_DISTRO_NAME" ]] || [[ -n "$WSL_INTEROP" ]] || [[ -f "/proc/sys/fs/binfmt_misc/WSLInterop" ]]; then
    IS_WSL=true
    print_warning "Running in WSL2 - additional audio setup may be required"
  elif grep -qi "microsoft.*WSL" /proc/version 2>/dev/null; then
    # Only match if both "microsoft" AND "WSL" are present (case-insensitive)
    IS_WSL=true
    print_warning "Running in WSL2 - additional audio setup may be required"
  fi

  if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    ARCH=$(uname -m)
    local macos_version=$(sw_vers -productVersion)
    print_success "Detected macOS $macos_version on $ARCH"
  elif [[ -f /etc/fedora-release ]]; then
    OS="fedora"
    ARCH=$(uname -m)
    local fedora_version=$(cat /etc/fedora-release | grep -oP '\d+' | head -1)
    print_success "Detected Fedora $fedora_version on $ARCH$([[ "$IS_WSL" == "true" ]] && echo " (WSL2)" || echo "")"
  elif [[ -f /etc/os-release ]]; then
    source /etc/os-release
    if [[ "$ID" == "ubuntu" ]] || [[ "$ID_LIKE" == *"ubuntu"* ]]; then
      OS="ubuntu"
      ARCH=$(uname -m)
      print_success "Detected Ubuntu $VERSION_ID on $ARCH$([[ "$IS_WSL" == "true" ]] && echo " (WSL2)" || echo "")"
    elif [[ "$ID" == "fedora" ]]; then
      OS="fedora"
      ARCH=$(uname -m)
      print_success "Detected Fedora $VERSION_ID on $ARCH$([[ "$IS_WSL" == "true" ]] && echo " (WSL2)" || echo "")"
    else
      print_error "Unsupported Linux distribution: $ID. Currently only Ubuntu and Fedora are supported."
    fi
  else
    print_error "Unsupported operating system: $OSTYPE"
  fi
}

check_xcode_tools() {
  print_step "Checking for Xcode Command Line Tools..."

  if xcode-select -p >/dev/null 2>&1; then
    XCODE_TOOLS_INSTALLED=true
    print_success "Xcode Command Line Tools are already installed"
  else
    print_warning "Xcode Command Line Tools not found"
  fi
}

install_xcode_tools() {
  if [ "$XCODE_TOOLS_INSTALLED" = false ]; then
    print_step "Installing Xcode Command Line Tools..."
    echo "This will open a dialog to install Xcode Command Line Tools."
    echo "Please follow the prompts and re-run this installer after installation completes."

    xcode-select --install

    print_warning "Please complete the Xcode Command Line Tools installation and re-run this installer."
    exit 0
  fi
}

check_homebrew() {
  print_step "Checking for Homebrew..."

  if command -v brew >/dev/null 2>&1; then
    HOMEBREW_INSTALLED=true
    print_success "Homebrew is already installed"
  else
    print_warning "Homebrew not found"
  fi
}

confirm_action() {
  local action="$1"
  echo ""
  echo "About to: $action"
  read -p "Continue? (y/n): " choice
  case $choice in
  [Yy]*) return 0 ;;
  *)
    echo "Skipping: $action"
    return 1
    ;;
  esac
}

install_homebrew() {
  if [ "$HOMEBREW_INSTALLED" = false ]; then
    if confirm_action "Install Homebrew (this will also install Xcode Command Line Tools)"; then
      print_step "Installing Homebrew..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

      # Add Homebrew to PATH for current session
      if [[ "$ARCH" == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
      else
        eval "$(/usr/local/bin/brew shellenv)"
      fi

      print_success "Homebrew installed successfully"

      # Update the status variables since Homebrew installs Xcode tools
      HOMEBREW_INSTALLED=true
      XCODE_TOOLS_INSTALLED=true
    else
      print_error "Homebrew is required for VoiceMode dependencies. Installation aborted."
    fi
  fi
}

check_system_dependencies() {
  print_step "Checking system dependencies..."

  if [[ "$OS" == "macos" ]]; then
    local packages=("node" "portaudio" "ffmpeg" "cmake" "coreutils")
    local missing_packages=()

    for package in "${packages[@]}"; do
      if brew list "$package" >/dev/null 2>&1; then
        print_success "$package is already installed"
      else
        missing_packages+=("$package")
      fi
    done

    if [ ${#missing_packages[@]} -eq 0 ]; then
      print_success "All system dependencies are already installed"
      return 0
    else
      echo "Missing packages: ${missing_packages[*]}"
      return 1
    fi
  elif [[ "$OS" == "fedora" ]]; then
    local packages=("nodejs" "portaudio-devel" "ffmpeg" "cmake" "python3-devel" "alsa-lib-devel")
    local missing_packages=()

    for package in "${packages[@]}"; do
      # Special handling for ffmpeg which might be installed from RPM Fusion
      if [[ "$package" == "ffmpeg" ]]; then
        if command -v ffmpeg >/dev/null 2>&1; then
          print_success "$package is already installed"
        else
          missing_packages+=("$package")
        fi
      elif rpm -q "$package" >/dev/null 2>&1; then
        print_success "$package is already installed"
      else
        missing_packages+=("$package")
      fi
    done

    if [ ${#missing_packages[@]} -eq 0 ]; then
      print_success "All system dependencies are already installed"
      return 0
    else
      echo "Missing packages: ${missing_packages[*]}"
      return 1
    fi
  elif [[ "$OS" == "ubuntu" ]]; then
    local packages=("nodejs" "npm" "portaudio19-dev" "ffmpeg" "cmake" "python3-dev" "libasound2-dev" "libasound2-plugins")
    local missing_packages=()

    for package in "${packages[@]}"; do
      if dpkg -l "$package" 2>/dev/null | grep -q '^ii'; then
        print_success "$package is already installed"
      else
        missing_packages+=("$package")
      fi
    done

    if [ ${#missing_packages[@]} -eq 0 ]; then
      print_success "All system dependencies are already installed"
      return 0
    else
      echo "Missing packages: ${missing_packages[*]}"
      return 1
    fi
  fi
}

install_system_dependencies() {
  if ! check_system_dependencies; then
    if [[ "$OS" == "macos" ]]; then
      if confirm_action "Install missing system dependencies via Homebrew"; then
        print_step "Installing system dependencies..."

        # Update Homebrew
        brew update

        # Install required packages
        local packages=("node" "portaudio" "ffmpeg" "cmake" "coreutils")

        for package in "${packages[@]}"; do
          if brew list "$package" >/dev/null 2>&1; then
            print_success "$package is already installed"
          else
            print_step "Installing $package..."
            brew install "$package"
            print_success "$package installed"
          fi
        done
      else
        print_warning "Skipping system dependencies. VoiceMode may not work properly without them."
      fi
    elif [[ "$OS" == "fedora" ]]; then
      if confirm_action "Install missing system dependencies via DNF"; then
        print_step "Installing system dependencies..."

        # Update package lists (ignore exit code as dnf check-update returns 100 when updates are available)
        sudo dnf check-update || true

        # Install required packages
        local packages=("nodejs" "portaudio-devel" "ffmpeg" "cmake" "python3-devel" "alsa-lib-devel")

        print_step "Installing packages: ${packages[*]}"
        sudo dnf install -y "${packages[@]}"
        print_success "System dependencies installed"
      else
        print_warning "Skipping system dependencies. VoiceMode may not work properly without them."
      fi
    elif [[ "$OS" == "ubuntu" ]]; then
      if confirm_action "Install missing system dependencies via APT"; then
        print_step "Installing system dependencies..."

        # Update package lists
        sudo apt update

        # Install required packages
        local packages=("nodejs" "npm" "portaudio19-dev" "ffmpeg" "cmake" "python3-dev" "libasound2-dev" "libasound2-plugins" "pulseaudio" "pulseaudio-utils")

        # Add WSL-specific packages if detected
        if [[ "$IS_WSL" == true ]]; then
          print_warning "WSL2 detected - installing additional audio packages"
          packages+=("libasound2-plugins" "pulseaudio")
        fi

        print_step "Installing packages: ${packages[*]}"
        sudo apt install -y "${packages[@]}"
        print_success "System dependencies installed"

        # WSL-specific audio setup
        if [[ "$IS_WSL" == true ]]; then
          print_step "Setting up WSL2 audio support..."

          # Start PulseAudio if not running
          if ! pgrep -x "pulseaudio" >/dev/null; then
            pulseaudio --start 2>/dev/null || true
            print_success "Started PulseAudio service"
          fi

          # Check audio devices
          if command -v pactl >/dev/null 2>&1; then
            if pactl list sources short 2>/dev/null | grep -q .; then
              print_success "Audio devices detected in WSL2"
            else
              print_warning "No audio devices detected. WSL2 audio setup may require:"
              echo "  1. Enable Windows microphone permissions for your terminal"
              echo "  2. Ensure WSL version is 2.3.26.0 or higher (run 'wsl --version')"
              echo "  3. See: https://github.com/mbailey/voicemode/blob/main/docs/troubleshooting/wsl2-microphone-access.md"
            fi
          fi
        fi
      else
        print_warning "Skipping system dependencies. VoiceMode may not work properly without them."
      fi
    fi
  fi
}

check_python() {
  print_step "Checking Python installation..."

  if command -v python3 >/dev/null 2>&1; then
    local python_version=$(python3 --version | cut -d' ' -f2)
    print_success "Python 3 found: $python_version"

    # Check if pip3 is available
    if command -v pip3 >/dev/null 2>&1; then
      print_success "pip3 is available"
    else
      print_error "pip3 not found. Please install pip for Python 3."
    fi
  else
    print_error "Python 3 not found. Please install Python 3 first."
  fi
}

install_uv() {
  if ! command -v uv >/dev/null 2>&1; then
    if confirm_action "Install UV (required for VoiceMode)"; then
      print_step "Installing UV..."

      # Install UV using the official installer
      curl -LsSf https://astral.sh/uv/install.sh | sh

      # Add UV to PATH for current session
      export PATH="$HOME/.local/bin:$PATH"

      # Verify installation immediately
      if ! command -v uv >/dev/null 2>&1; then
        print_error "UV installation failed - command not found after installation"
        return 1
      fi

      # Test uv actually works
      if ! uv --version >/dev/null 2>&1; then
        print_error "UV installation failed - command not working"
        return 1
      fi

      # Add to shell profile if not already there
      local shell_profile=""
      if [[ "$SHELL" == *"zsh"* ]]; then
        shell_profile="$HOME/.zshrc"
      elif [[ "$SHELL" == *"bash"* ]]; then
        if [[ "$OS" == "macos" ]]; then
          shell_profile="$HOME/.bash_profile"
        else
          shell_profile="$HOME/.bashrc"
        fi
      fi

      if [ -n "$shell_profile" ] && [ -f "$shell_profile" ]; then
        if ! grep -q "\.local/bin" "$shell_profile"; then
          echo 'export PATH="$HOME/.local/bin:$PATH"' >>"$shell_profile"
          print_success "Added UV to PATH in $shell_profile"
          # Source the profile to make UV immediately available
          source "$shell_profile"
          print_success "Loaded $shell_profile to update PATH"
        fi
      fi

      print_success "UV installed and verified successfully"
    else
      print_error "UV is required for VoiceMode. Installation aborted."
      return 1
    fi
  else
    print_success "UV is already installed"

    # Even if already installed, verify it works
    if ! uv --version >/dev/null 2>&1; then
      print_error "UV is installed but not working properly"
      return 1
    fi
  fi
}

install_voicemode() {
  print_step "Installing VoiceMode..."

  # Install voice-mode package with uv tool install
  if uv tool install --upgrade --force voice-mode; then
    print_success "VoiceMode installed successfully"

    # Update shell to ensure PATH includes UV tools
    print_step "Updating shell PATH configuration..."
    if uv tool update-shell; then
      print_success "Shell PATH updated"

      # Export PATH for current session
      export PATH="$HOME/.local/bin:$PATH"

      # Source shell profile for immediate availability
      if [[ "$SHELL" == *"zsh"* ]] && [[ -f "$HOME/.zshrc" ]]; then
        source "$HOME/.zshrc" 2>/dev/null || true
      elif [[ "$SHELL" == *"bash"* ]] && [[ -f "$HOME/.bashrc" ]]; then
        source "$HOME/.bashrc" 2>/dev/null || true
      fi
    else
      print_warning "Could not update shell PATH automatically"
    fi

    # Verify the voicemode command is available
    if command -v voicemode >/dev/null 2>&1; then
      print_success "VoiceMode command verified: voicemode"
      return 0
    else
      print_warning "VoiceMode installed but command not immediately available"
      echo "  You may need to restart your shell or run: source ~/.bashrc"
      return 0
    fi
  else
    print_error "Failed to install VoiceMode"
    return 1
  fi
}

setup_local_npm() {
  print_step "Setting up local npm configuration..."

  # Set up npm to use local directory (no sudo required)
  mkdir -p "$HOME/.npm-global"
  npm config set prefix "$HOME/.npm-global"

  # Add to PATH for current session
  export PATH="$HOME/.npm-global/bin:$PATH"

  # Add to shell profile if not already there
  local shell_profile=""
  if [[ "$SHELL" == *"zsh"* ]]; then
    shell_profile="$HOME/.zshrc"
  elif [[ "$SHELL" == *"bash"* ]]; then
    if [[ "$OS" == "macos" ]]; then
      shell_profile="$HOME/.bash_profile"
    else
      shell_profile="$HOME/.bashrc"
    fi
  fi

  if [ -n "$shell_profile" ] && [ -f "$shell_profile" ]; then
    if ! grep -q "\.npm-global/bin" "$shell_profile"; then
      echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >>"$shell_profile"
      print_success "Added npm global bin to PATH in $shell_profile"
      # Source the profile to make npm immediately available
      source "$shell_profile"
      print_success "Loaded $shell_profile to update PATH"
    fi
  fi

  print_success "Local npm configuration complete"
}

setup_shell_completion() {
  # Safe shell completion setup that checks command availability at runtime
  # This prevents shell startup errors by only enabling completions when the command exists

  # Detect current shell
  local shell_type=""
  local shell_rc=""

  if [[ -n "${BASH_VERSION:-}" ]]; then
    shell_type="bash"
    shell_rc="$HOME/.bashrc"
  elif [[ -n "${ZSH_VERSION:-}" ]]; then
    shell_type="zsh"
    shell_rc="$HOME/.zshrc"
  else
    # Try to detect from SHELL environment variable
    case "${SHELL:-}" in
    */bash)
      shell_type="bash"
      shell_rc="$HOME/.bashrc"
      ;;
    */zsh)
      shell_type="zsh"
      shell_rc="$HOME/.zshrc"
      ;;
    *)
      print_warning "Unsupported shell for completion: ${SHELL:-unknown}"
      echo "  VoiceMode completion supports bash and zsh only"
      return 1
      ;;
    esac
  fi

  if [[ -z "$shell_type" ]]; then
    print_debug "Could not detect shell type for completion setup"
    return 1
  fi

  print_step "Setting up shell completion for $shell_type..."

  # Set up completion based on shell type
  if [[ "$shell_type" == "bash" ]]; then
    # Check for existing bash-completion support
    local has_bash_completion=false
    local user_completions_dir="${XDG_DATA_HOME:-$HOME/.local/share}/bash-completion/completions"

    # Check if bash-completion is installed
    if [[ -f "/usr/share/bash-completion/bash_completion" ]] ||
      [[ -f "/etc/bash_completion" ]] ||
      (command -v brew >/dev/null 2>&1 && brew list bash-completion@2 >/dev/null 2>&1); then
      has_bash_completion=true
    fi

    if [[ "$has_bash_completion" == true ]]; then
      # Install completion file to user directory
      mkdir -p "$user_completions_dir"

      # Generate and save completion file
      if command -v voicemode >/dev/null 2>&1; then
        _VOICEMODE_COMPLETE=bash_source voicemode >"$user_completions_dir/voicemode" 2>/dev/null
        if [[ -s "$user_completions_dir/voicemode" ]]; then
          print_success "Installed bash completion to $user_completions_dir/"
          echo "   Tab completion will be available in new bash sessions"
        else
          rm -f "$user_completions_dir/voicemode"
          # Fallback to shell RC method
          has_bash_completion=false
        fi
      fi
    fi

    if [[ "$has_bash_completion" == false ]]; then
      # Fallback: Add to shell RC file
      local completion_line='# VoiceMode shell completion
if command -v voicemode >/dev/null 2>&1; then
    eval "$(_VOICEMODE_COMPLETE=bash_source voicemode)"
fi'

      if [[ -f "$shell_rc" ]] && grep -q "_VOICEMODE_COMPLETE\|_VOICE_MODE_COMPLETE" "$shell_rc" 2>/dev/null; then
        print_success "Shell completion already configured in $shell_rc"
      else
        echo "" >>"$shell_rc"
        echo "$completion_line" >>"$shell_rc"
        print_success "Added shell completion to $shell_rc"
        echo "   Tab completion will be available in new shell sessions"
      fi
    fi
  elif [[ "$shell_type" == "zsh" ]]; then
    # Detect best location for zsh completions
    local completion_dir=""
    local needs_fpath_update=false

    # Check for Homebrew on macOS
    if [[ "$OS" == "macos" ]] && command -v brew >/dev/null 2>&1; then
      local brew_prefix=$(brew --prefix)
      if [[ -d "$brew_prefix/share/zsh/site-functions" ]]; then
        completion_dir="$brew_prefix/share/zsh/site-functions"
        print_debug "Using Homebrew zsh completion directory"
      fi
    fi

    # Check standard locations if not found
    if [[ -z "$completion_dir" ]]; then
      for dir in \
        "/usr/local/share/zsh/site-functions" \
        "/usr/share/zsh/site-functions" \
        "$HOME/.zsh/completions"; do
        if [[ -d "$dir" ]] || [[ "$dir" == "$HOME/.zsh/completions" ]]; then
          completion_dir="$dir"
          if [[ "$dir" == "$HOME/.zsh/completions" ]]; then
            needs_fpath_update=true
          fi
          break
        fi
      done
    fi

    # Create directory if needed
    if [[ ! -d "$completion_dir" ]]; then
      mkdir -p "$completion_dir"
    fi

    # Generate and install completion file (with underscore prefix)
    if command -v voicemode >/dev/null 2>&1; then
      _VOICEMODE_COMPLETE=zsh_source voicemode >"$completion_dir/_voicemode" 2>/dev/null
      if [[ -s "$completion_dir/_voicemode" ]]; then
        print_success "Installed zsh completion to $completion_dir/"

        # Update fpath if using custom directory
        if [[ "$needs_fpath_update" == true ]]; then
          local fpath_line="fpath=($completion_dir \$fpath)"
          if [[ -f "$shell_rc" ]] && ! grep -q "$completion_dir" "$shell_rc" 2>/dev/null; then
            echo "" >>"$shell_rc"
            echo "# Add VoiceMode completions to fpath" >>"$shell_rc"
            echo "$fpath_line" >>"$shell_rc"
            print_success "Added $completion_dir to fpath in $shell_rc"
          fi
        fi
        echo "   Tab completion will be available in new zsh sessions"
      else
        # Fallback to shell RC method
        rm -f "$completion_dir/_voicemode"
        local completion_line='# VoiceMode shell completion
if command -v voicemode >/dev/null 2>&1; then
    eval "$(_VOICEMODE_COMPLETE=zsh_source voicemode)"
fi'

        if [[ -f "$shell_rc" ]] && grep -q "_VOICEMODE_COMPLETE\|_VOICE_MODE_COMPLETE" "$shell_rc" 2>/dev/null; then
          print_success "Shell completion already configured in $shell_rc"
        else
          echo "" >>"$shell_rc"
          echo "$completion_line" >>"$shell_rc"
          print_success "Added shell completion to $shell_rc"
          echo "   Tab completion will be available in new shell sessions"
        fi
      fi
    fi
  fi

  return 0
}

configure_claude_voicemode() {
  if command -v claude >/dev/null 2>&1; then
    # Check if voicemode is already configured
    if claude mcp list 2>/dev/null | grep -q -e "voicemode" -e "voice-mode"; then
      print_success "VoiceMode is already configured in Claude Code"
      setup_shell_completion
      return 0
    else
      if confirm_action "Add VoiceMode to Claude Code (adds MCP server)"; then
        print_step "Adding VoiceMode to Claude Code..."

        # Try with --scope flag first (newer versions)
        if claude mcp add --scope user -- voicemode voice-mode 2>/dev/null; then
          print_success "VoiceMode added to Claude Code"
          setup_shell_completion
          return 0
        else
          print_error "Failed to add VoiceMode to Claude Code"
          return 1
        fi
      else
        print_step "Skipping VoiceMode configuration"
        echo "You can configure it later with:"
        echo "  claude mcp add --scope user -- voicemode voice-mode"
        return 1
      fi
    fi
  else
    print_warning "Claude Code not found. Please install it first to use VoiceMode."
    return 1
  fi
}

install_claude_if_needed() {
  if ! command -v claude >/dev/null 2>&1; then
    if confirm_action "Install Claude Code (required for VoiceMode)"; then
      print_step "Installing Claude Code..."
      if command -v npm >/dev/null 2>&1; then
        npm install -g @anthropic-ai/claude-code
        print_success "Claude Code installed"
      else
        print_error "npm not found. Please install Node.js first."
        return 1
      fi
    else
      print_warning "Claude Code is required for VoiceMode. Skipping configuration."
      return 1
    fi
  fi
  return 0
}

# Service installation functions
check_voice_mode_cli() {
  # Check for locally installed voicemode command
  # This should be available after uv tool install

  if [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]]; then
    echo "[DEBUG] Checking for voicemode CLI availability..." >&2
  fi

  # Check if voicemode command is available
  if command -v voicemode >/dev/null 2>&1; then
    print_success "VoiceMode CLI is available" >&2
    echo "voicemode"
    return 0
  else
    print_warning "VoiceMode CLI not found" >&2
    echo "  Please ensure VoiceMode was installed correctly with 'uv tool install --upgrade --force voice-mode'" >&2
    echo "  You may need to restart your shell or run: source ~/.bashrc" >&2
    return 1
  fi
}

install_service() {
  local service_name="$1"
  local voice_mode_cmd="$2"
  local description="$3"

  print_step "Installing $description..."

  # Debug mode check
  if [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]]; then
    echo "[DEBUG] Checking service command: $voice_mode_cmd $service_name --help"
  fi

  # Check if the service subcommand exists first
  # Redirect stderr to stdout and check for the actual help output
  # This handles cases where Python warnings are printed to stderr
  local help_output
  local help_exit_code
  help_output=$(timeout 30 $voice_mode_cmd $service_name --help 2>&1 || true)
  help_exit_code=$?

  if [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]]; then
    echo "[DEBUG] Help command exit code: $help_exit_code"
    echo "[DEBUG] Help output length: ${#help_output} bytes"
    echo "[DEBUG] First 500 chars of help output:"
    echo "$help_output" | head -c 500
    echo ""
    echo "[DEBUG] Checking for 'Commands:' in output..."
  fi

  if ! echo "$help_output" | grep -q "Commands:"; then
    print_warning "$description service command not available"
    if [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]]; then
      echo "[DEBUG] 'Commands:' not found in help output"
      echo "[DEBUG] Full help output:"
      echo "$help_output"
    fi
    return 1
  fi

  if [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]]; then
    echo "[DEBUG] Service command check passed"
  fi

  # Install with timeout and capture output
  local temp_log=$(mktemp)
  local install_success=false

  print_step "Running: $voice_mode_cmd $service_name install --auto-enable"
  if timeout 600 $voice_mode_cmd $service_name install --auto-enable 2>&1 | tee "$temp_log"; then
    install_success=true
  fi

  # Check for specific success/failure indicators
  if [[ "$install_success" == true ]] && ! grep -qi "error\|failed\|traceback" "$temp_log"; then
    print_success "$description installed successfully"
    rm -f "$temp_log"
    return 0
  else
    print_warning "$description installation may have failed"
    echo "Last few lines of output:"
    tail -10 "$temp_log" | sed 's/^/  /'
    rm -f "$temp_log"
    return 1
  fi
}

install_all_services() {
  local voice_mode_cmd="$1"
  local success_count=0
  local total_count=3

  print_step "Installing all VoiceMode services..."

  # Install each service independently
  if install_service "whisper" "$voice_mode_cmd" "Whisper (Speech-to-Text)"; then
    ((success_count++))
    # CoreML acceleration setup for Apple Silicon Macs
    # DISABLED: CoreML build issues - users getting errors at 3:30am
    # setup_coreml_acceleration
  fi

  if install_service "kokoro" "$voice_mode_cmd" "Kokoro (Text-to-Speech)"; then
    ((success_count++))
  fi

  if install_service "livekit" "$voice_mode_cmd" "LiveKit (Real-time Communication)"; then
    ((success_count++))
  fi

  # Report results
  echo ""
  if [[ $success_count -eq $total_count ]]; then
    print_success "All voice services installed successfully!"
  elif [[ $success_count -gt 0 ]]; then
    print_warning "$success_count of $total_count services installed successfully"
    echo "   Check error messages above for failed installations"
  else
    print_error "No services were installed successfully"
  fi
}

install_services_selective() {
  local voice_mode_cmd="$1"

  if confirm_action "Install Whisper (Speech-to-Text)"; then
    install_service "whisper" "$voice_mode_cmd" "Whisper"
    # CoreML acceleration setup for Apple Silicon Macs
    # DISABLED: CoreML build issues - users getting errors at 3:30am
    # setup_coreml_acceleration
  fi

  if confirm_action "Install Kokoro (Text-to-Speech)"; then
    install_service "kokoro" "$voice_mode_cmd" "Kokoro"
  fi

  if confirm_action "Install LiveKit (Real-time Communication)"; then
    install_service "livekit" "$voice_mode_cmd" "LiveKit"
  fi
}

verify_voice_mode_after_mcp() {
  print_step "Verifying VoiceMode CLI availability after MCP configuration..."

  # Give a moment for any caching to settle
  sleep 2

  # Check voice-mode CLI availability
  local voice_mode_cmd
  if ! voice_mode_cmd=$(check_voice_mode_cli); then
    print_warning "VoiceMode CLI not available yet. This could be due to:"
    echo "  • PATH not updated in current shell"
    echo "  • VoiceMode not installed yet"
    echo "  • Need to restart shell for PATH updates"
    echo ""
    echo "You can install services manually later with:"
    echo "  voicemode whisper install"
    echo "  voicemode kokoro install"
    echo "  voicemode livekit install"
    return 1
  fi

  print_success "VoiceMode CLI verified: $voice_mode_cmd"
  return 0
}

install_voice_services() {
  # Verify voice-mode CLI availability first
  if ! verify_voice_mode_after_mcp; then
    return 1
  fi

  # Get the verified command
  local voice_mode_cmd
  voice_mode_cmd=$(check_voice_mode_cli)

  echo ""
  echo -e "${BLUE}🎤 VoiceMode Services${NC}"
  echo ""
  echo "VoiceMode can install local services for the best experience:"
  echo "  • Whisper - Fast local speech-to-text (no cloud required)"
  echo "  • Kokoro - Natural text-to-speech with multiple voices"
  echo "  • LiveKit - Real-time voice communication server"
  echo ""
  echo "Benefits:"
  echo "  • Privacy - All processing happens locally"
  echo "  • Speed - No network latency"
  echo "  • Reliability - Works offline"
  echo ""
  echo "Note: Service installation may take several minutes and requires internet access."
  echo ""

  # Quick mode or selective
  read -p "Install all recommended services? [Y/n/s]: " choice
  case $choice in
  [Ss]*)
    # Selective mode
    install_services_selective "$voice_mode_cmd"
    ;;
  [Nn]*)
    print_warning "Skipping service installation. VoiceMode will use cloud services."
    ;;
  *)
    # Default: install all
    install_all_services "$voice_mode_cmd"
    ;;
  esac
}

show_banner() {
  # Clear screen for clean presentation
  clear

  # Display VoiceMode ASCII art
  echo ""
  echo -e "${ORANGE}${BOLD}"
  cat <<'EOF'
    ╔════════════════════════════════════════════╗
    ║                                            ║
    ║   ██╗   ██╗ ██████╗ ██╗ ██████╗███████╗    ║
    ║   ██║   ██║██╔═══██╗██║██╔════╝██╔════╝    ║
    ║   ██║   ██║██║   ██║██║██║     █████╗      ║
    ║   ╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝      ║
    ║    ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗    ║
    ║     ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝    ║
    ║                                            ║
    ║   ███╗   ███╗ ██████╗ ██████╗ ███████╗     ║
    ║   ████╗ ████║██╔═══██╗██╔══██╗██╔════╝     ║
    ║   ██╔████╔██║██║   ██║██║  ██║█████╗       ║
    ║   ██║╚██╔╝██║██║   ██║██║  ██║██╔══╝       ║
    ║   ██║ ╚═╝ ██║╚██████╔╝██████╔╝███████╗     ║
    ║   ╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝     ║
    ║                                            ║
    ║     🎙️  VoiceMode for Claude Code  🤖      ║
    ║                                            ║
    ╚════════════════════════════════════════════╝
EOF
  echo -e "${NC}"

  echo -e "${BOLD}Talk to Claude like a colleague, not a chatbot.${NC}"
  echo ""
  echo -e "${DIM}Transform your AI coding experience with natural voice conversations.${NC}"
  echo ""
}

setup_coreml_acceleration() {
  # Check if we're on Apple Silicon Mac
  if [[ "$OS" == "macos" ]] && [[ "$ARCH" == "arm64" ]]; then
    echo ""
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${BLUE}${BOLD}🚀 CoreML Acceleration Available${NC}"
    echo ""
    echo "Your Mac supports CoreML acceleration for Whisper!"
    echo ""
    echo -e "${GREEN}Benefits:${NC}"
    echo "  • 2-3x faster transcription than Metal-only"
    echo "  • Lower CPU usage during speech recognition"
    echo "  • Better battery life on MacBooks"
    echo ""
    echo -e "${YELLOW}Requirements:${NC}"
    echo "  • PyTorch package (~2.5GB download)"
    echo "  • CoreMLTools and dependencies (~100MB)"
    echo "  • Full Xcode installation (~10GB from Mac App Store)"
    echo ""

    # Check for Xcode
    XCODE_AVAILABLE=false
    if [[ -f "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/coremlc" ]]; then
      echo -e "${GREEN}✓${NC} Full Xcode detected"
      XCODE_AVAILABLE=true
    else
      echo -e "${YELLOW}⚠${NC} Full Xcode not found (Command Line Tools alone won't work)"
      echo ""
      echo "  Without Xcode, Whisper will still use Metal acceleration (fast)"
      echo "  To enable CoreML later:"
      echo "    1. Install Xcode from Mac App Store"
      echo "    2. Open Xcode once to accept license"
      echo "    3. Run: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
      echo "    4. Run: voicemode whisper model install base"
    fi

    echo ""

    # Only offer to install if Xcode is available
    if [[ "$XCODE_AVAILABLE" == "true" ]]; then
      echo -e "${BOLD}Install CoreML acceleration now?${NC}"
      echo ""
      echo "This will download PyTorch (~2.5GB) and configure CoreML."
      echo "You can always add this later with: voicemode whisper model install base"
      echo ""
      read -p "Install CoreML acceleration? [y/N]: " -n 1 -r
      echo ""

      if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        print_step "Installing CoreML dependencies..."
        echo "This may take several minutes due to the large download size..."
        echo ""

        # Get the voice mode command
        local voice_mode_cmd
        if ! voice_mode_cmd=$(check_voice_mode_cli); then
          print_warning "VoiceMode CLI not available for CoreML setup"
          echo "You can retry later with:"
          echo "  voicemode whisper model install base"
          return 0
        fi

        # Run the whisper model install command with torch installation
        # Note: Using default model (base) which is a good balance of speed and accuracy
        if echo "y" | $voice_mode_cmd whisper model install base; then
          print_success "CoreML acceleration installed successfully!"
          echo ""
          echo "Whisper will now use CoreML for maximum performance."
        else
          print_warning "CoreML installation encountered issues."
          echo "Whisper will use Metal acceleration (still fast)."
          echo ""
          echo "You can retry later with:"
          echo "  voicemode whisper model install base"
        fi
      else
        echo ""
        echo "Skipping CoreML setup. Whisper will use Metal acceleration."
        echo ""
        echo -e "${DIM}To add CoreML later, run: voicemode whisper model install base${NC}"
      fi
    else
      echo -e "${DIM}Skipping CoreML - Xcode not installed${NC}"
      echo "Whisper will use Metal acceleration (still performs well)"
    fi

    echo ""
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  fi
}

main() {
  # Initialize logging first
  init_logging
  
  # Set up error trap
  trap 'handle_installation_error "$BASH_COMMAND"' ERR
  
  # Show banner first
  show_banner

  # Check for debug mode
  if [[ "${VOICEMODE_INSTALL_DEBUG:-}" == "true" ]]; then
    echo -e "${YELLOW}[DEBUG MODE ENABLED]${NC}"
    echo ""
    log_info "Debug mode enabled"
  fi
  
  # Test mode - trigger error for testing
  if [[ "${VOICEMODE_TEST_ERROR:-}" == "true" ]]; then
    echo -e "${YELLOW}[TEST MODE] Simulating installation error...${NC}"
    log_info "Test mode - triggering error"
    false # This will trigger the error trap
  fi

  # Anonymous analytics beacon (privacy-respecting)
  # Only tracks: install event, OS type, timestamp
  # No personal data collected
  {
    if command -v curl >/dev/null 2>&1; then
      # Simple beacon to track installs
      # Uses Goatcounter's pixel tracking endpoint
      curl -s "https://getvoicemode.goatcounter.com/count?p=/install&t=Install%20Script" \
        -H "User-Agent: VoiceMode-Installer/${OS:-unknown}" \
        -H "Referer: https://getvoicemode.com/install.sh" \
        >/dev/null 2>&1 || true
    fi
  } &

  # Pre-flight checks
  detect_os

  # Early sudo caching for service installation (Linux only)
  if [[ "$OS" == "linux" ]] && command -v sudo >/dev/null 2>&1; then
    print_step "Requesting administrator access for system configuration..."
    if ! sudo -v; then
      print_warning "Administrator access declined. Some features may not be available."
    fi
  fi

  # OS-specific setup
  if [[ "$OS" == "macos" ]]; then
    check_homebrew
    # Skip Xcode tools check if Homebrew will handle it
    if [ "$HOMEBREW_INSTALLED" = false ]; then
      install_homebrew # This installs Xcode tools automatically
    fi
  fi

  check_python
  install_uv

  # Install dependencies
  install_system_dependencies

  # Install VoiceMode package locally
  install_voicemode

  # Setup npm for non-macOS systems
  if [[ "$OS" != "macos" ]]; then
    setup_local_npm
  fi

  # Install Claude Code if needed, then configure VoiceMode
  if install_claude_if_needed; then
    if configure_claude_voicemode; then
      # VoiceMode configured successfully
      echo ""
      echo "🎉 VoiceMode is ready! You can use voice commands with:"
      echo "  claude converse"
      echo ""

      # Offer to install services
      install_voice_services
    else
      print_warning "VoiceMode configuration was skipped or failed."
      echo ""
      echo "You can manually configure VoiceMode later with:"
      echo "  claude mcp add voice-mode -- voicemode"
      echo ""
      echo "Then install services with:"
      echo "  voicemode whisper install"
      echo "  voicemode kokoro install"
      echo "  voicemode livekit install"
    fi
  fi

  # WSL-specific instructions
  if [[ "$IS_WSL" == true ]]; then
    echo ""
    echo -e "${YELLOW}WSL2 Audio Setup:${NC}"
    echo "VoiceMode requires microphone access in WSL2. If you encounter audio issues:"
    echo "  1. Enable Windows microphone permissions for your terminal app"
    echo "  2. Ensure PulseAudio is running: pulseaudio --start"
    echo "  3. Test audio devices: python3 -m sounddevice"
    echo "  4. See troubleshooting guide: https://github.com/mbailey/voicemode/blob/main/docs/troubleshooting/wsl2-microphone-access.md"
  fi

  echo ""
  echo "For more information, visit: https://github.com/mbailey/voicemode"
  
  # Log successful completion
  log_info "Installation completed successfully"
  log_info "Log file saved at: $LOG_FILE"
}

# Run main function
main "$@"
