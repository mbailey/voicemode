"""Installation tool for LiveKit server"""

import os
import sys
import platform
import subprocess
import shutil
import logging
import tempfile
import tarfile
from pathlib import Path
from typing import Dict, Any, Optional, Union
import asyncio
import aiohttp

from voice_mode.server import mcp
from voice_mode.config import SERVICE_AUTO_ENABLE
from voice_mode.utils.version_helpers import (
    get_git_tags, get_latest_stable_tag, get_current_version,
    checkout_version, is_version_installed
)
from voice_mode.utils.migration_helpers import auto_migrate_if_needed

logger = logging.getLogger("voice-mode")


async def download_livekit_binary(version: str, install_dir: Path) -> bool:
    """Download LiveKit binary from GitHub releases"""
    system = platform.system()
    machine = platform.machine().lower()
    
    # Map architecture names
    if machine in ["x86_64", "amd64"]:
        arch = "amd64"
    elif machine in ["aarch64", "arm64"]:
        arch = "arm64"
    else:
        logger.error(f"Unsupported architecture: {machine}")
        return False
    
    # Construct download URL
    if system == "Linux":
        filename = f"livekit_{version}_linux_{arch}.tar.gz"
    elif system == "Darwin":
        filename = f"livekit_{version}_darwin_{arch}.tar.gz"
    else:
        logger.error(f"Unsupported platform: {system}")
        return False
    
    url = f"https://github.com/livekit/livekit/releases/download/{version}/{filename}"
    logger.info(f"Downloading LiveKit from: {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to download: HTTP {response.status}")
                    return False
                
                # Download to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp_file:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        tmp_file.write(chunk)
                    tmp_path = tmp_file.name
        
        # Extract binary
        logger.info("Extracting LiveKit binary...")
        with tarfile.open(tmp_path, "r:gz") as tar:
            # Find the livekit-server binary
            for member in tar.getmembers():
                if member.name.endswith("livekit-server"):
                    member.name = "livekit-server"  # Rename to simple name
                    tar.extract(member, install_dir)
                    break
        
        # Make executable
        binary_path = install_dir / "livekit-server"
        binary_path.chmod(0o755)
        
        # Clean up
        os.unlink(tmp_path)
        
        logger.info(f"LiveKit binary installed to: {binary_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error downloading LiveKit: {e}")
        return False


def create_livekit_config(config_path: Path, port: int = 7880) -> None:
    """Create LiveKit configuration file"""
    config_content = f"""# LiveKit Server Configuration
# Development mode with standard devkey/secret

port: {port}
rtc:
  port_range_start: 50000
  port_range_end: 60000
  use_external_ip: false

# Development keys - DO NOT USE IN PRODUCTION
keys:
  devkey: secret

# Logging
log_level: info

# Room settings
room:
  auto_create: true
  empty_timeout: 300
  max_participants: 10
"""
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_content)
    logger.info(f"Created LiveKit config at: {config_path}")


@mcp.tool()
async def livekit_install(
    install_dir: Optional[str] = None,
    port: Union[int, str] = 7880,
    force_reinstall: Union[bool, str] = False,
    auto_enable: Optional[Union[bool, str]] = None,
    version: str = "latest"
) -> Dict[str, Any]:
    """
    Install LiveKit server with development configuration.
    
    Uses dev mode with standard devkey/secret for easy setup.
    
    Args:
        install_dir: Directory to install LiveKit (default: ~/.voicemode/services/livekit)
        port: Port for LiveKit server (default: 7880)
        force_reinstall: Force reinstallation even if already installed
        auto_enable: Enable service after install. If None, uses VOICEMODE_SERVICE_AUTO_ENABLE config.
        version: Version to install (default: "latest" for latest stable release)
    
    Returns:
        Installation status with server configuration details
    """
    try:
        # Set default install directory
        voicemode_dir = os.path.expanduser("~/.voicemode")
        os.makedirs(voicemode_dir, exist_ok=True)
        
        if install_dir is None:
            install_dir = os.path.join(voicemode_dir, "services", "livekit")
        else:
            install_dir = os.path.expanduser(install_dir)
        
        install_path = Path(install_dir)
        
        # Check system
        system = platform.system()
        
        # Convert port to integer if provided as string
        if isinstance(port, str):
            try:
                port = int(port)
            except ValueError:
                logger.warning(f"Invalid port value '{port}', using default 7880")
                port = 7880
        
        # Handle string boolean conversions
        if isinstance(force_reinstall, str):
            force_reinstall = force_reinstall.lower() in ("true", "1", "yes", "on")
        if isinstance(auto_enable, str):
            auto_enable = auto_enable.lower() in ("true", "1", "yes", "on")
        
        # Determine auto_enable default
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE
        
        # Check if already installed
        binary_path = install_path / "livekit-server"
        if binary_path.exists() and not force_reinstall:
            # Check version
            try:
                result = subprocess.run(
                    [str(binary_path), "--version"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                current_version = result.stdout.strip()
                return {
                    "success": True,
                    "install_path": str(install_path),
                    "binary_path": str(binary_path),
                    "already_installed": True,
                    "version": current_version,
                    "message": f"LiveKit already installed. Version: {current_version}. Use force_reinstall=True to reinstall."
                }
            except Exception:
                pass
        
        # Remove existing installation if force_reinstall
        if force_reinstall and install_path.exists():
            logger.info(f"Removing existing installation at {install_path}")
            shutil.rmtree(install_path)
        
        # Create installation directory
        install_path.mkdir(parents=True, exist_ok=True)
        
        # Platform-specific installation
        if system == "Darwin" and shutil.which("brew"):
            # macOS with Homebrew
            logger.info("Installing LiveKit via Homebrew...")
            
            # Update brew
            subprocess.run(["brew", "update"], check=True)
            
            # Install or upgrade LiveKit
            if force_reinstall:
                subprocess.run(["brew", "reinstall", "livekit"], check=True)
            else:
                subprocess.run(["brew", "install", "livekit"], check=True)
            
            # Find installed binary
            brew_binary = shutil.which("livekit-server")
            if not brew_binary:
                return {
                    "success": False,
                    "error": "LiveKit installed via brew but binary not found in PATH"
                }
            
            # Create symlink in our directory
            if binary_path.exists():
                binary_path.unlink()
            binary_path.symlink_to(brew_binary)
            
            logger.info(f"Linked LiveKit binary from: {brew_binary}")
            
        elif system == "Linux":
            # Linux - use install script or direct download
            if version == "latest":
                # Try official install script first
                logger.info("Installing LiveKit via official script...")
                try:
                    # Download and run install script
                    install_script = """
                    curl -sSL https://get.livekit.io | bash -s -- --install-dir={install_dir}
                    """.format(install_dir=install_path)
                    
                    subprocess.run(install_script, shell=True, check=True)
                    
                    if not binary_path.exists():
                        # Script might have installed to /usr/local/bin
                        system_binary = Path("/usr/local/bin/livekit-server")
                        if system_binary.exists():
                            # Copy to our directory
                            shutil.copy2(system_binary, binary_path)
                            binary_path.chmod(0o755)
                
                except Exception as e:
                    logger.warning(f"Install script failed: {e}, trying direct download...")
                    version = "v1.7.2"  # Fallback to known good version
            
            # Direct download if needed
            if not binary_path.exists():
                # Get available versions
                if version == "latest":
                    tags = get_git_tags("https://github.com/livekit/livekit")
                    if tags:
                        version = get_latest_stable_tag(tags)
                    else:
                        version = "v1.7.2"  # Fallback version
                
                # Download binary
                success = await download_livekit_binary(version, install_path)
                if not success:
                    return {
                        "success": False,
                        "error": "Failed to download LiveKit binary"
                    }
        
        else:
            return {
                "success": False,
                "error": f"Unsupported platform: {system}. Please install LiveKit manually."
            }
        
        # Verify installation
        if not binary_path.exists():
            return {
                "success": False,
                "error": "LiveKit binary not found after installation"
            }
        
        # Get version
        try:
            result = subprocess.run(
                [str(binary_path), "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            installed_version = result.stdout.strip()
        except Exception:
            installed_version = "unknown"
        
        # Create configuration
        config_dir = Path(voicemode_dir) / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "livekit.yaml"
        create_livekit_config(config_path, port)
        
        # Create log directory
        log_dir = Path(voicemode_dir) / "logs" / "livekit"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Install service
        from voice_mode.tools.service import install_service, enable_service
        
        service_result = await install_service("livekit")
        if not service_result["success"]:
            logger.warning(f"Service installation failed: {service_result.get('error', 'Unknown error')}")
        
        # Enable service if requested (auto-enable by default)
        service_enabled = False
        if auto_enable and service_result["success"]:
            enable_result = await enable_service("livekit")
            # enable_service returns a string message, not a dict
            if isinstance(enable_result, str) and "✅" in enable_result:
                service_enabled = True
                logger.info(f"LiveKit service auto-enabled: {enable_result}")
            else:
                logger.warning(f"Service enable failed: {enable_result}")
        
        return {
            "success": True,
            "install_path": str(install_path),
            "binary_path": str(binary_path),
            "config_path": str(config_path),
            "log_dir": str(log_dir),
            "version": installed_version,
            "port": port,
            "dev_key": "devkey",
            "dev_secret": "secret",
            "url": f"ws://localhost:{port}",
            "service_installed": service_result["success"],
            "service_enabled": service_enabled,
            "auto_enable": auto_enable,
            "message": f"LiveKit {installed_version} installed successfully in dev mode"
        }
        
    except Exception as e:
        logger.error(f"LiveKit installation failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Installation failed: {str(e)}"
        }


# CLI entry point
async def main():
    """CLI entry point for testing"""
    result = await livekit_install()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())