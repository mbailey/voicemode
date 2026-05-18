#!/usr/bin/env bash
# VoiceMode Installer
# https://getvoicemode.com/install.sh
#
# Usage:
#   curl -fsSL https://getvoicemode.com/install.sh | bash
#   curl -fsSL https://getvoicemode.com/install.sh | bash -s -- -y  # non-interactive
#   curl -fsSL https://getvoicemode.com/install.sh | bash -s -- -y --voice mlx
#
# This script installs VoiceMode and its dependencies.
# It supports macOS and Linux (Debian/Ubuntu, Fedora).
#
# Voice backend (--voice, or VOICEMODE_VOICE_ENGINE env):
#   mlx    Apple Silicon only: mlx-audio (one fast on-device server for
#          STT+TTS). Recommended on Apple Silicon; opt-in.
#   local  whisper.cpp + Kokoro (cross-platform; the only option off
#          Apple Silicon).
#   skip   install no local voice services.
# Default when unset: interactive prompt; non-interactive skips the large
# local-voice download (unchanged prior behaviour).

set -o nounset -o pipefail -o errexit

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

VOICEMODE_PACKAGE="voice-mode"
INTERACTIVE=true

# Voice backend selection (VM-1330).
#   ""     - not explicitly chosen; resolved interactively or by the
#            non-interactive skip default (preserves prior behaviour).
#   mlx    - Apple Silicon only: install mlx-audio (one fast on-device
#            server for STT+TTS) and point VoiceMode at it.
#   local  - whisper.cpp + Kokoro (the cross-platform path; the only
#            option off Apple Silicon).
#   skip   - install no local voice services.
# Explicit --voice (or VOICEMODE_VOICE_ENGINE env) takes precedence over
# the interactive prompt and the non-interactive skip default.
VOICE_CHOICE="${VOICEMODE_VOICE_ENGINE:-}"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -y|--yes)
            INTERACTIVE=false
            shift
            ;;
        --voice)
            VOICE_CHOICE="${2:-}"
            shift 2
            ;;
        --voice=*)
            VOICE_CHOICE="${1#*=}"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Validate --voice value early so a typo fails fast rather than silently
# falling through to the wrong backend.
case "$VOICE_CHOICE" in
    ""|mlx|local|skip) ;;
    *)
        echo "Error: --voice must be one of: mlx, local, skip (got: '$VOICE_CHOICE')" >&2
        exit 1
        ;;
esac

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
        ORANGE=""
        BOLD=""
        DIM=""
        RESET=""
    else
        RED=$'\033[0;31m'
        GREEN=$'\033[0;32m'
        YELLOW=$'\033[0;33m'
        BLUE=$'\033[0;34m'
        ORANGE=$'\033[38;2;255;135;0m' # Claude Code orange (24-bit truecolor, theme-independent)
        BOLD=$'\033[1m'
        DIM=$'\033[2m'
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
# Large orange ASCII-art banner (Claude Code orange, ANSI 256-color 208)
show_logo() {
    echo ""
    printf '%s' "${ORANGE}${BOLD}"
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
    ║         VoiceMode for Claude Code          ║
    ║                                            ║
    ╚════════════════════════════════════════════╝
EOF
    printf '%s\n' "${RESET}"
    echo ""
    echo "${BOLD}Talk to Claude like a colleague, not a chatbot.${RESET}"
    echo ""
    echo "${DIM}Transform your AI coding experience with natural voice conversations.${RESET}"
    echo ""
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check if /dev/tty is available for interactive input
# (needed for curl|bash and SSH scenarios)
tty_available() {
    # Try to open /dev/tty in a subshell to avoid polluting fd table
    # and to properly suppress errors
    (exec </dev/tty) 2>/dev/null
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

# Install all macOS prerequisites (Homebrew + packages + uv) with single confirmation
install_macos_prerequisites() {
    local -a packages=(portaudio ffmpeg)
    local -a to_install=()
    local need_homebrew=false
    local need_uv=false
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

    # Check if uv is installed
    if ! command_exists uv; then
        need_uv=true
    else
        ok "uv found"
    fi

    # If nothing to install, we're done
    if [[ "$need_homebrew" == "false" ]] && [[ ${#to_install[@]} -eq 0 ]] && [[ "$need_uv" == "false" ]]; then
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
    if [[ "$need_uv" == "true" ]]; then
        echo "    - uv (Python package manager)"
    fi

    # Prompt for confirmation in interactive mode (only if TTY available)
    if [[ "$INTERACTIVE" == "true" ]] && tty_available; then
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
    elif [[ "$need_homebrew" == "true" ]] && { [[ "$INTERACTIVE" == "false" ]] || ! tty_available; }; then
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
        ok "Packages installed"
    fi

    # Install uv if needed
    if [[ "$need_uv" == "true" ]]; then
        info "Installing uv..."
        if command_exists curl; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        elif command_exists wget; then
            wget -qO- https://astral.sh/uv/install.sh | sh
        else
            die "Neither curl nor wget found. Cannot install uv."
        fi
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        if command_exists uv; then
            ok "uv installed"
        else
            die "uv installation failed"
        fi
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

# Install required system packages on Linux (+ uv)
# These are needed for compiling webrtcvad and simpleaudio
install_linux_deps() {
    local distro="$1"
    local -a all_packages missing_packages
    local SUDO=""
    local pkg
    local need_uv=false

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

    # Check if uv is installed
    if ! command_exists uv; then
        need_uv=true
    else
        ok "uv found"
    fi

    # If everything is installed, we're done
    if [[ ${#missing_packages[@]} -eq 0 ]] && [[ "$need_uv" == "false" ]]; then
        ok "All dependencies already installed"
        return 0
    fi

    # Show what needs to be installed
    info "The following will be installed:"
    for pkg in "${missing_packages[@]}"; do
        echo "    - $pkg"
    done
    if [[ "$need_uv" == "true" ]]; then
        echo "    - uv (Python package manager)"
    fi

    # Prompt for confirmation in interactive mode (only if TTY available)
    if [[ "$INTERACTIVE" == "true" ]] && tty_available; then
        echo ""
        read -r -p "Install these? [Y/n] " response </dev/tty
        case "$response" in
            [nN][oO]|[nN])
                warn "Skipping dependency installation"
                warn "VoiceMode may not work correctly without these packages"
                return 0
                ;;
        esac
    fi

    # Install missing packages
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
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
        ok "Packages installed"
    fi

    # Install uv if needed
    if [[ "$need_uv" == "true" ]]; then
        info "Installing uv..."
        if command_exists curl; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        elif command_exists wget; then
            wget -qO- https://astral.sh/uv/install.sh | sh
        else
            die "Neither curl nor wget found. Cannot install uv."
        fi
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        if command_exists uv; then
            ok "uv installed"
        else
            die "uv installation failed"
        fi
    fi
}

# -----------------------------------------------------------------------------
# System Dependencies (orchestration)
# -----------------------------------------------------------------------------

# Install all system dependencies for the detected platform
install_system_deps() {
    local os="$1"
    local arch="$2"
    local distro

    case "$os" in
        macos)
            ok "Platform: macOS ($arch)"
            install_macos_prerequisites
            ;;
        linux)
            distro=$(detect_linux_distro)
            ok "Platform: Linux/$distro ($arch)"
            install_linux_deps "$distro"
            # ARM64 Linux needs Rust via rustup for Kokoro dependencies
            if [[ "$arch" == "arm64" ]]; then
                ensure_rust
            fi
            ;;
        windows)
            die "Windows is not yet supported. Please use WSL2 instead."
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Local Voice Services (Whisper & Kokoro)
# -----------------------------------------------------------------------------

# Check if Whisper STT is installed
is_whisper_installed() {
    [[ -d "$HOME/.voicemode/services/whisper" ]]
}

# Check if Kokoro TTS is installed
is_kokoro_installed() {
    [[ -d "$HOME/.voicemode/services/kokoro" ]]
}

# -----------------------------------------------------------------------------
# mlx-audio (Apple Silicon) -- VM-1330
# -----------------------------------------------------------------------------
#
# mlx-audio is a single MLX-native server (STT + TTS + clone-voice) that runs
# on its OWN port 8890. We point VoiceMode at it by putting the mlx-audio URL
# FIRST in the preference-ordered base-URL lists (OpenAI kept as a trailing
# cloud fallback). This mirrors voice_mode/tools/mlx_audio/install.py and the
# VM-1088 port decision (8880 compat-shim was rejected).
#
# IMPORTANT (VM-1318 gate): mlx-audio is RECOMMENDED + opt-in on Apple
# Silicon. It is NOT the silent non-interactive default until the
# security/project-health review (VM-1318) clears. Selection is explicit:
# an interactive choice, or an explicit --voice mlx flag.

MLX_AUDIO_PORT=8890

# True only on Apple Silicon (macOS arm64) -- the hard gate per ADR VM-1086.
# Mirrors voice_mode/tools/mlx_audio/install.py::_is_apple_silicon and the
# assess_voice_capability "excellent" branch.
is_apple_silicon() {
    local os="$1"
    local arch="$2"
    [[ "$os" == "macos" && "$arch" == "arm64" ]]
}

# Check if mlx-audio is already installed (uv-tool entry point present).
is_mlx_audio_installed() {
    [[ -x "$HOME/.local/bin/mlx_audio.server" ]]
}

# Point VoiceMode at mlx-audio's own port (8890) by making it the FIRST
# entry in the preference-ordered base-URL lists. OpenAI stays as the
# trailing cloud fallback so a cold mlx-audio still degrades gracefully.
# Uses the existing `voicemode config set` primitive (writes
# ~/.voicemode/voicemode.env) -- no fragile shell-side env munging.
configure_mlx_audio_urls() {
    local mlx_url="http://127.0.0.1:${MLX_AUDIO_PORT}/v1"
    local urls="${mlx_url},https://api.openai.com/v1"

    info "Pointing VoiceMode at mlx-audio (port ${MLX_AUDIO_PORT})..."
    if voicemode config set VOICEMODE_TTS_BASE_URLS "$urls" \
        && voicemode config set VOICEMODE_STT_BASE_URLS "$urls"; then
        ok "VoiceMode configured to prefer mlx-audio (OpenAI cloud fallback kept)"
    else
        warn "Could not write mlx-audio base-URL config"
        warn "Set it later with:"
        warn "  voicemode config set VOICEMODE_TTS_BASE_URLS \"$urls\""
        warn "  voicemode config set VOICEMODE_STT_BASE_URLS \"$urls\""
    fi
}

# Install mlx-audio via the existing CLI primitive, then wire the config.
# install.sh stays a thin orchestrator -- the uv tool install + bundled
# patch + launchd plist all live in `voicemode service install mlx-audio`
# (mlx_audio_install()), which is already Apple-Silicon-gated.
install_mlx_audio() {
    if is_mlx_audio_installed; then
        ok "mlx-audio already installed"
        configure_mlx_audio_urls
        return 0
    fi

    echo ""
    echo "${BOLD}Installing mlx-audio${RESET} (Apple Silicon on-device STT+TTS)"
    info "One fast MLX server on port ${MLX_AUDIO_PORT} -- no Xcode, no source compile."
    info "No models are downloaded now; weights pull on first voice use."

    if voicemode service install mlx-audio; then
        ok "mlx-audio installed"
        configure_mlx_audio_urls
    else
        warn "mlx-audio installation failed - retry with: voicemode service install mlx-audio"
        warn "Falling back to whisper.cpp + Kokoro is also available:"
        warn "  voicemode whisper install && voicemode kokoro install"
        return 1
    fi
}

# Resolve the voice backend choice on Apple Silicon.
# Precedence (per VM-1330 plan):
#   explicit --voice flag  >  interactive prompt  >  non-interactive skip
# Echoes one of: mlx | local | skip
# Honors the VM-1318 gate: non-interactive without an explicit --voice
# stays "skip" (the prior behaviour) -- mlx is never the silent default.
resolve_apple_silicon_choice() {
    # Explicit flag / env wins outright.
    if [[ -n "$VOICE_CHOICE" ]]; then
        echo "$VOICE_CHOICE"
        return 0
    fi

    if [[ "$INTERACTIVE" == "true" ]] && tty_available; then
        echo "" >&2
        echo "${BOLD}Install local voice services${RESET} -- text-to-speech & speech-to-text?" >&2
        echo "" >&2
        echo "  [1] mlx-audio -- fast TTS/STT + voice cloning (models load on first use)   ${GREEN}(recommended)${RESET}" >&2
        echo "  [2] whisper.cpp + Kokoro -- classic, cross-platform (~3 GB)" >&2
        echo "  [3] no thanks" >&2
        echo "" >&2
        local response
        read -r -p "> " response </dev/tty
        case "$response" in
            ""|1)     echo "mlx" ;;
            2)        echo "local" ;;
            3|[sS])   echo "skip" ;;
            *)
                warn "Unrecognised choice '$response' -- defaulting to recommended (mlx-audio)" >&2
                echo "mlx"
                ;;
        esac
        return 0
    fi

    # Non-interactive, no explicit choice: preserve prior behaviour
    # (skip the large download). Do NOT silently default to mlx --
    # that decision is gated by VM-1318.
    echo "skip"
}

# Assess system capability for local voice services
# Returns: "excellent", "good", or "limited"
assess_voice_capability() {
    local os="$1"
    local arch="$2"
    local ram_gb=0

    # Get RAM in GB
    case "$os" in
        macos)
            ram_gb=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
            ;;
        linux)
            ram_gb=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 / 1024 ))
            ;;
    esac

    # Apple Silicon Mac: excellent (unified memory, Neural Engine)
    # Everything else: depends on RAM
    if [[ "$os" == "macos" && "$arch" == "arm64" ]]; then
        echo "excellent"
    elif [[ $ram_gb -ge 16 ]]; then
        echo "good"
    elif [[ $ram_gb -ge 8 ]]; then
        echo "limited"
    else
        echo "limited"
    fi
}

# Get human-readable capability message
get_capability_message() {
    local capability="$1"

    case "$capability" in
        excellent)
            echo "Local voice services should run excellently on this system."
            ;;
        good)
            echo "Local voice services should run well on this system."
            ;;
        limited)
            echo "Local voice services may be slow on this system."
            ;;
    esac
}

# Print the install status of each voice engine relevant to this platform,
# mirroring the existing "✓ ... already installed" style. On Apple Silicon
# this also covers mlx-audio; off Apple Silicon mlx-audio is never mentioned
# (it can't run there).
show_voice_status() {
    local os="$1"
    local arch="$2"

    echo ""
    echo "${BOLD}Local voice services${RESET}"

    if is_apple_silicon "$os" "$arch"; then
        if is_mlx_audio_installed; then
            ok "mlx-audio already installed"
        else
            info "${DIM}–${RESET} mlx-audio not installed"
        fi
    fi

    if is_whisper_installed; then
        ok "Whisper STT already installed"
    else
        info "${DIM}–${RESET} Whisper STT not installed"
    fi

    if is_kokoro_installed; then
        ok "Kokoro TTS already installed"
    else
        info "${DIM}–${RESET} Kokoro TTS not installed"
    fi
}

# Prompt user to install local voice services
install_voice_services() {
    local os="$1"
    local arch="$2"
    local whisper_installed=false
    local kokoro_installed=false
    # Set when the user has explicitly opted into whisper.cpp+Kokoro
    # (Apple-Silicon "local" choice). Lets that choice bypass the legacy
    # confirmation prompt / non-interactive skip below and install directly.
    local explicit_local=false

    # STATUS DISPLAY FIRST: report what's installed before any prompt.
    show_voice_status "$os" "$arch"

    # Track install state (status already printed above; don't re-print
    # the per-service "already installed" lines a second time).
    if is_whisper_installed; then
        whisper_installed=true
    fi

    if is_kokoro_installed; then
        kokoro_installed=true
    fi

    # --- Apple Silicon: recommend mlx-audio, offer explicit choice (VM-1330) ---
    # This MUST run BEFORE the "both already installed" early-return below:
    # a user who already has whisper.cpp + Kokoro (very common -- anyone on a
    # prior release) should still be offered mlx-audio as a switch/upgrade.
    # Their existing whisper/Kokoro install is left in place as a fallback;
    # choosing mlx just installs mlx-audio and re-points the BASE_URLs.
    # Off Apple Silicon this whole block is skipped and behaviour is exactly
    # as before (the both-installed early-return still applies).
    if is_apple_silicon "$os" "$arch"; then
        # Already-satisfied shortcut: if mlx-audio is installed and the user
        # did NOT explicitly force a backend, there's nothing to ask. Just
        # idempotently re-point VoiceMode at mlx-audio and finish cleanly
        # (mirrors the whisper+Kokoro both-installed early-return). An
        # explicit --voice (or VOICEMODE_VOICE_ENGINE) always wins and
        # bypasses this shortcut so the user can force the other path.
        if is_mlx_audio_installed && [[ -z "$VOICE_CHOICE" ]]; then
            configure_mlx_audio_urls
            ok "mlx-audio already installed and configured -- all set, nothing to do"
            return 0
        fi

        local choice
        choice=$(resolve_apple_silicon_choice)
        case "$choice" in
            mlx)
                # mlx-audio is independent of whisper/Kokoro -- it installs
                # and points BASE_URLs at port 8890 even when whisper+Kokoro
                # are already present (existing install kept as fallback).
                # If the mlx-audio install fails, fall through to the
                # existing whisper.cpp + Kokoro path rather than leaving the
                # user with no voice backend.
                if install_mlx_audio; then
                    return 0
                fi
                warn "Continuing with whisper.cpp + Kokoro fallback"
                ;;
            skip)
                info "Skipping local voice services"
                info "Install mlx-audio later with: voicemode service install mlx-audio"
                info "  (or whisper.cpp + Kokoro: voicemode whisper install && voicemode kokoro install)"
                return 0
                ;;
            local)
                # Fall through to the existing whisper.cpp + Kokoro flow,
                # and treat it as an explicit opt-in so the legacy prompt /
                # non-interactive skip is bypassed. If both are already
                # installed the legacy flow's per-service skips make this a
                # no-op (correct: nothing to reinstall).
                explicit_local=true
                ;;
        esac
    fi

    # If both are installed, nothing to do. (On Apple Silicon we only reach
    # here when the user chose "local" with nothing left to install, or the
    # mlx install fell back -- the whisper+Kokoro early-return is still right.)
    if [[ "$whisper_installed" == "true" && "$kokoro_installed" == "true" ]]; then
        return 0
    fi

    # Assess system capability
    local capability
    capability=$(assess_voice_capability "$os" "$arch")
    local capability_msg
    capability_msg=$(get_capability_message "$capability")

    # Show info about local voice services
    echo ""
    echo "${BOLD}Local Voice Services${RESET}"
    info "$capability_msg"

    # Build list of what would be installed
    local services_to_install=""
    if [[ "$whisper_installed" == "false" ]]; then
        services_to_install="Whisper (speech-to-text)"
    fi
    if [[ "$kokoro_installed" == "false" ]]; then
        if [[ -n "$services_to_install" ]]; then
            services_to_install="$services_to_install, Kokoro (text-to-speech)"
        else
            services_to_install="Kokoro (text-to-speech)"
        fi
    fi

    # Show download size estimate
    local download_size="~3GB"
    if [[ "$whisper_installed" == "false" && "$kokoro_installed" == "false" ]]; then
        download_size="~3GB total"
    elif [[ "$whisper_installed" == "false" ]]; then
        download_size="~1.5GB"
    elif [[ "$kokoro_installed" == "false" ]]; then
        download_size="~1.5GB"
    fi

    info "Available: $services_to_install ($download_size download)"

    # Honor an explicit backend choice on ANY platform (VM-1330). On
    # non-Apple-Silicon, `--voice mlx` is not viable -- mlx-audio is
    # Apple-Silicon-only -- so warn and treat it as the local path.
    if [[ "$explicit_local" == "false" && -n "$VOICE_CHOICE" ]]; then
        case "$VOICE_CHOICE" in
            skip)
                info "Skipping local voice services (--voice skip)"
                info "Install later with: voicemode whisper install && voicemode kokoro install"
                return 0
                ;;
            mlx)
                # Reached here only if NOT Apple Silicon (the arm64 mac
                # branch above handles mlx and returns). mlx-audio can't
                # run here -- fall back to whisper.cpp + Kokoro.
                warn "mlx-audio requires Apple Silicon (macOS arm64); using whisper.cpp + Kokoro instead"
                explicit_local=true
                ;;
            local)
                explicit_local=true
                ;;
        esac
    fi

    # Prompt for installation. An explicit local opt-in bypasses both the
    # confirmation prompt and the non-interactive skip default.
    if [[ "$explicit_local" == "true" ]]; then
        info "Installing whisper.cpp + Kokoro (explicitly selected)"
    elif [[ "$INTERACTIVE" == "true" ]] && tty_available; then
        echo ""
        read -r -p "Install local voice services? [Y/n] " response </dev/tty
        case "$response" in
            [nN][oO]|[nN])
                info "Skipping local voice services"
                info "You can install them later with: voicemode whisper install && voicemode kokoro install"
                return 0
                ;;
        esac
    else
        # Non-interactive: skip voice services by default (they're large downloads)
        info "Skipping local voice services (non-interactive mode)"
        info "Install later with: voicemode whisper install && voicemode kokoro install"
        return 0
    fi

    # Install Whisper if needed
    if [[ "$whisper_installed" == "false" ]]; then
        info "Installing Whisper STT..."
        if voicemode whisper install; then
            ok "Whisper STT installed"
        else
            warn "Whisper installation failed - you can retry with: voicemode whisper install"
        fi
    fi

    # Install Kokoro if needed
    if [[ "$kokoro_installed" == "false" ]]; then
        info "Installing Kokoro TTS..."
        if voicemode kokoro install; then
            ok "Kokoro TTS installed"
        else
            warn "Kokoro installation failed - you can retry with: voicemode kokoro install"
        fi
    fi
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

    # Install system dependencies (includes uv)
    install_system_deps "$os" "$arch"

    # Install and verify VoiceMode
    install_voicemode
    verify_voicemode

    # Offer to install local voice services
    install_voice_services "$os" "$arch"

    show_next_steps
}

main "$@"
