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
# Output helpers
# -----------------------------------------------------------------------------

# Print error message to stderr and exit
die() {
    echo "Error: $1" >&2
    exit 1
}

# Print status message with checkmark
ok() {
    echo "✓ $1"
}

# Print warning message
warn() {
    echo "⚠️  $1"
}

# Print info message (for progress)
info() {
    echo "  $1"
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

# Ensure Homebrew is available (macOS only)
# Homebrew requires sudo for initial installation
ensure_homebrew() {
    if command_exists brew; then
        ok "Homebrew found"
        return 0
    fi

    if [[ "$INTERACTIVE" != "true" ]]; then
        die "Homebrew not found. Install Homebrew first, then re-run:
    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"

Non-interactive mode cannot install Homebrew (requires sudo)."
    fi

    warn "Homebrew not found"
    info "Homebrew is required on macOS for system dependencies."
    echo ""
    read -r -p "Install Homebrew now? [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY])
            info "Installing Homebrew (may require sudo)..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            if command_exists brew; then
                ok "Homebrew installed"
            else
                die "Homebrew installation failed"
            fi
            ;;
        *)
            die "Homebrew is required. Please install it manually:
    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            ;;
    esac
}

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

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    local os arch

    # Detect platform
    os=$(detect_os)
    arch=$(detect_arch)

    # Display header
    echo ""
    echo "🎙️  VoiceMode Installer"
    echo ""

    # Show detected platform
    case "$os" in
        macos)
            ok "Platform: macOS ($arch)"
            ;;
        linux)
            local distro
            distro=$(detect_linux_distro)
            ok "Platform: Linux/$distro ($arch)"
            ;;
        windows)
            die "Windows is not yet supported. Please use WSL2 instead."
            ;;
    esac

    # Check prerequisites
    case "$os" in
        macos)
            ensure_homebrew
            ;;
        linux)
            # Linux uses system package manager directly, no Homebrew needed
            ;;
    esac
    ensure_uv

    # Placeholder for VoiceMode installation (impl-003)
    echo ""
    info "Prerequisites satisfied. VoiceMode installation coming in next feature."
    echo ""
}

main "$@"
