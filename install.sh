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

    # Placeholder for subsequent features
    echo ""
    info "Platform detection complete. Further installation steps coming soon."
    echo ""
}

main "$@"
