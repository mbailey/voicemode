#!/usr/bin/env bash
# VoiceMode Installer
# https://getvoicemode.com/install.sh
#
# Usage:
#   curl -fsSL https://getvoicemode.com/install.sh | bash
#   curl -fsSL https://getvoicemode.com/install.sh | bash -s -- -y  # non-interactive
#
# This script installs VoiceMode and its dependencies.
# It supports macOS and Linux (Debian/Ubuntu, Fedora).

set -o nounset -o pipefail -o errexit

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

VOICEMODE_PACKAGE="voice-mode"
INTERACTIVE=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -y|--yes)
            INTERACTIVE=false
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Color Support
# -----------------------------------------------------------------------------

# Respect NO_COLOR environment variable (see https://no-color.org/)
# Also disable colors when not connected to a terminal
setup_colors() {
    if [[ -n "${NO_COLOR:-}" ]] || [[ ! -t 1 ]]; then
        # No colors
        RED=""
        GREEN=""
        YELLOW=""
        BLUE=""
        BOLD=""
        RESET=""
    else
        RED=$'\033[0;31m'
        GREEN=$'\033[0;32m'
        YELLOW=$'\033[0;33m'
        BLUE=$'\033[0;34m'
        BOLD=$'\033[1m'
        RESET=$'\033[0m'
    fi
}

# Initialize colors
setup_colors

# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------

# Print error message to stderr and exit
die() {
    echo "${RED}Error:${RESET} $1" >&2
    exit 1
}

# Print status message with checkmark
ok() {
    echo "${GREEN}✓${RESET} $1"
}

# Print warning message
warn() {
    echo "${YELLOW}⚠${RESET}  $1"
}

# Print info message (for progress)
info() {
    echo "  $1"
}

# Display VoiceMode logo
# Compact 3-line version that fits in ~45 columns
show_logo() {
    echo ""
    echo "${BOLD}██╗   ██╗ ██████╗ ██╗ ██████╗███████╗${RESET}"
    echo "${BOLD}██║   ██║██╔═══██╗██║██╔════╝██╔════╝${RESET}   ${BLUE}MODE${RESET}"
    echo "${BOLD} ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗${RESET}"
    echo ""
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# -----------------------------------------------------------------------------
# Platform Detection
# -----------------------------------------------------------------------------

detect_os() {
    case "$(uname -s)" in
        Darwin)
            echo "macos"
            ;;
        Linux)
            echo "linux"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "windows"
            ;;
        *)
            die "Unsupported operating system: $(uname -s)"
            ;;
    esac
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64)
            echo "x86_64"
            ;;
        arm64|aarch64)
            echo "arm64"
            ;;
        armv7l)
            echo "armv7"
            ;;
        *)
            die "Unsupported architecture: $(uname -m)"
            ;;
    esac
}

detect_linux_distro() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        case "$ID" in
            ubuntu|debian|pop|linuxmint|elementary)
                echo "debian"
                ;;
            fedora|rhel|centos|rocky|alma)
                echo "fedora"
                ;;
            arch|manjaro)
                echo "arch"
                ;;
            *)
                # Check for ID_LIKE as fallback
                case "${ID_LIKE:-}" in
                    *debian*)
                        echo "debian"
                        ;;
                    *fedora*|*rhel*)
                        echo "fedora"
                        ;;
                    *)
                        echo "unknown"
                        ;;
                esac
                ;;
        esac
    else
        echo "unknown"
    fi
}

# -----------------------------------------------------------------------------
# Prerequisite Installation
# -----------------------------------------------------------------------------

# Ensure uv package manager is available
# uv can be installed without sudo
ensure_uv() {
    if command_exists uv; then
        ok "uv found"
        return 0
    fi

    info "Installing uv package manager..."
    if command_exists curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command_exists wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        die "Neither curl nor wget found. Cannot install uv."
    fi

    # Add uv to PATH for this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if command_exists uv; then
        ok "uv installed"
    else
        die "uv installation failed. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
    fi
}

# Ensure Rust is available (for ARM64 Kokoro dependencies)
# Uses rustup for latest version since distro packages are often too old
ensure_rust() {
    # Check if Rust is already installed and recent enough (1.82+)
    if command_exists rustc; then
        local rust_version
        rust_version=$(rustc --version | sed -E 's/rustc ([0-9]+\.[0-9]+).*/\1/')
        local major minor
        major=$(echo "$rust_version" | cut -d. -f1)
        minor=$(echo "$rust_version" | cut -d. -f2)
        if [[ "$major" -gt 1 ]] || { [[ "$major" -eq 1 ]] && [[ "$minor" -ge 82 ]]; }; then
            ok "Rust $rust_version found"
            return 0
        fi
        info "Rust $rust_version is too old (need 1.82+), installing via rustup..."
    else
        info "Installing Rust via rustup..."
    fi

    if command_exists curl; then
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
    elif command_exists wget; then
        wget -qO- https://sh.rustup.rs | sh -s -- -y --no-modify-path
    else
        die "Neither curl nor wget found. Cannot install Rust."
    fi

    # Add cargo to PATH for this session
    export PATH="$HOME/.cargo/bin:$PATH"

    if command_exists rustc; then
        ok "Rust installed via rustup"
    else
        die "Rust installation failed. Please install manually: https://rustup.rs/"
    fi
}

# -----------------------------------------------------------------------------
# macOS System Dependencies
# -----------------------------------------------------------------------------

# Install all macOS prerequisites (Homebrew + packages) with single confirmation
install_macos_prerequisites() {
    local -a packages=(portaudio ffmpeg)
    local -a to_install=()
    local need_homebrew=false
    local pkg

    # Check if Homebrew is installed
    if ! command_exists brew; then
        need_homebrew=true
        # If no Homebrew, we'll need all packages too
        to_install=("${packages[@]}")
    else
        ok "Homebrew found"
        # Check which packages are missing
        for pkg in "${packages[@]}"; do
            if ! brew list "$pkg" &>/dev/null; then
                to_install+=("$pkg")
            fi
        done
    fi

    # If nothing to install, we're done
    if [[ "$need_homebrew" == "false" ]] && [[ ${#to_install[@]} -eq 0 ]]; then
        ok "All dependencies already installed"
        return 0
    fi

    # Show what will be installed
    info "The following will be installed:"
    if [[ "$need_homebrew" == "true" ]]; then
        echo "    - Homebrew (package manager)"
    fi
    for pkg in "${to_install[@]}"; do
        echo "    - $pkg"
    done

    # Prompt for confirmation in interactive mode
    if [[ "$INTERACTIVE" == "true" ]]; then
        echo ""
        read -r -p "Proceed with installation? [Y/n] " response </dev/tty
        case "$response" in
            [nN][oO]|[nN])
                if [[ "$need_homebrew" == "true" ]]; then
                    die "Homebrew is required for VoiceMode on macOS"
                fi
                warn "Skipping package installation"
                warn "VoiceMode may not work correctly without these packages"
                return 0
                ;;
        esac
    elif [[ "$need_homebrew" == "true" ]]; then
        # Non-interactive mode can't install Homebrew (needs sudo)
        die "Homebrew not found. Install it first, then re-run:
    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    fi

    # Install Homebrew if needed
    if [[ "$need_homebrew" == "true" ]]; then
        info "Installing Homebrew (may require password)..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for this session (Apple Silicon uses /opt/homebrew)
        local brew_path=""
        if [[ -x /opt/homebrew/bin/brew ]]; then
            brew_path="/opt/homebrew/bin/brew"
        elif [[ -x /usr/local/bin/brew ]]; then
            brew_path="/usr/local/bin/brew"
        fi

        if [[ -n "$brew_path" ]]; then
            eval "$($brew_path shellenv)"

            # Persist to shell profile for future sessions
            local shell_profile=""
            if [[ -n "${ZSH_VERSION:-}" ]] || [[ "$SHELL" == */zsh ]]; then
                shell_profile="$HOME/.zprofile"
            else
                shell_profile="$HOME/.bash_profile"
            fi

            local shellenv_line="eval \"\$($brew_path shellenv)\""
            if ! grep -q "brew shellenv" "$shell_profile" 2>/dev/null; then
                echo "" >> "$shell_profile"
                echo "# Homebrew" >> "$shell_profile"
                echo "$shellenv_line" >> "$shell_profile"
            fi
        fi

        if command_exists brew; then
            ok "Homebrew installed"
        else
            die "Homebrew installation failed"
        fi
    fi

    # Install packages if needed
    if [[ ${#to_install[@]} -gt 0 ]]; then
        info "Installing packages..."
        brew install "${to_install[@]}"
        ok "Dependencies installed"
    fi
}

# -----------------------------------------------------------------------------
# Linux System Dependencies
# -----------------------------------------------------------------------------

# Check if a package is installed (distro-specific)
is_package_installed() {
    local distro="$1"
    local package="$2"

    case "$distro" in
        debian)
            dpkg -s "$package" &>/dev/null
            ;;
        fedora)
            rpm -q "$package" &>/dev/null
            ;;
        arch)
            pacman -Q "$package" &>/dev/null
            ;;
        *)
            return 1
            ;;
    esac
}

# Install required system packages on Linux
# These are needed for compiling webrtcvad and simpleaudio
install_linux_deps() {
    local distro="$1"
    local -a all_packages missing_packages
    local SUDO=""
    local pkg

    # Use sudo if not running as root and sudo is available
    if [[ "$(id -u)" != "0" ]]; then
        if command_exists sudo; then
            SUDO="sudo"
        else
            die "This script requires root privileges or sudo. Please run as root or install sudo."
        fi
    fi

    # Define packages per distro
    case "$distro" in
        debian)
            all_packages=(python3-dev gcc libasound2-dev libportaudio2 ffmpeg)
            # ARM64 needs g++ for Kokoro's mojimoji dependency
            if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "arm64" ]]; then
                all_packages+=(g++)
            fi
            ;;
        fedora)
            all_packages=(python3-devel gcc alsa-lib-devel portaudio ffmpeg)
            # ARM64 needs g++ for Kokoro's mojimoji dependency
            if [[ "$(uname -m)" == "aarch64" || "$(uname -m)" == "arm64" ]]; then
                all_packages+=(gcc-c++)
            fi
            ;;
        arch)
            all_packages=(python gcc alsa-lib portaudio ffmpeg)
            # Arch gcc package includes g++, no extras needed
            ;;
        *)
            warn "Unknown Linux distro. Please install build dependencies manually:"
            echo "  - C compiler (gcc)"
            echo "  - Python development headers"
            echo "  - ALSA development libraries"
            echo "  - PortAudio library"
            echo "  - FFmpeg"
            return 0
            ;;
    esac

    # Check which packages are missing
    missing_packages=()
    for pkg in "${all_packages[@]}"; do
        if ! is_package_installed "$distro" "$pkg"; then
            missing_packages+=("$pkg")
        fi
    done

    # If all packages are installed, we're done
    if [[ ${#missing_packages[@]} -eq 0 ]]; then
        ok "All dependencies already installed"
        return 0
    fi

    # Show what needs to be installed
    info "The following packages need to be installed:"
    for pkg in "${missing_packages[@]}"; do
        echo "    - $pkg"
    done

    # Prompt for confirmation in interactive mode
    if [[ "$INTERACTIVE" == "true" ]]; then
        echo ""
        read -r -p "Install these packages? [Y/n] " response </dev/tty
        case "$response" in
            [nN][oO]|[nN])
                warn "Skipping dependency installation"
                warn "VoiceMode may not work correctly without these packages"
                return 0
                ;;
        esac
    fi

    # Install missing packages
    info "Installing packages..."
    case "$distro" in
        debian)
            export DEBIAN_FRONTEND=noninteractive
            $SUDO apt-get update -qq >/dev/null
            $SUDO apt-get install -y -qq "${missing_packages[@]}" >/dev/null
            ;;
        fedora)
            $SUDO dnf install -y -q "${missing_packages[@]}" >/dev/null
            ;;
        arch)
            $SUDO pacman -S --noconfirm -q "${missing_packages[@]}" >/dev/null
            ;;
    esac
    ok "Dependencies installed"
}

# -----------------------------------------------------------------------------
# VoiceMode Installation
# -----------------------------------------------------------------------------

# Install VoiceMode using uv
install_voicemode() {
    info "Installing VoiceMode..."

    local output
    # Use uv tool install for isolated tool installation
    # Capture output to check for "already installed" message
    if output=$(uv tool install "$VOICEMODE_PACKAGE" 2>&1); then
        if echo "$output" | grep -q "already installed"; then
            ok "VoiceMode already installed"
        else
            ok "VoiceMode installed"
        fi
    else
        # Installation failed
        if command_exists voicemode; then
            # Already installed but uv failed (shouldn't happen normally)
            ok "VoiceMode already installed"
        else
            echo "$output" >&2
            die "VoiceMode installation failed"
        fi
    fi
}

# Verify VoiceMode installation and show version
verify_voicemode() {
    # Refresh PATH to pick up newly installed tools
    export PATH="$HOME/.local/bin:$PATH"

    if ! command_exists voicemode; then
        die "VoiceMode command not found after installation.
Please ensure ~/.local/bin is in your PATH:
    export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi

    local version
    version=$(voicemode --version 2>/dev/null | sed 's/VoiceMode, version //' || echo "unknown")
    ok "VoiceMode $version ready"
}

# Display next steps for the user
show_next_steps() {
    echo ""
    echo "Next steps:"
    echo "  voicemode --help   Show available commands"
    echo "  voicemode status   Check service status"
    echo ""
    echo "Documentation: https://getvoicemode.com/docs"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    local os arch distro

    # Detect platform
    os=$(detect_os)
    arch=$(detect_arch)

    # Display logo
    show_logo

    # Show detected platform
    case "$os" in
        macos)
            ok "Platform: macOS ($arch)"
            ;;
        linux)
            distro=$(detect_linux_distro)
            ok "Platform: Linux/$distro ($arch)"
            ;;
        windows)
            die "Windows is not yet supported. Please use WSL2 instead."
            ;;
    esac

    # Check prerequisites and install dependencies
    case "$os" in
        macos)
            install_macos_prerequisites
            ;;
        linux)
            install_linux_deps "$distro"
            # ARM64 Linux needs Rust via rustup for Kokoro dependencies
            if [[ "$arch" == "arm64" ]]; then
                ensure_rust
            fi
            ;;
    esac
    ensure_uv

    # Install and verify VoiceMode
    install_voicemode
    verify_voicemode
    show_next_steps
}

main "$@"
