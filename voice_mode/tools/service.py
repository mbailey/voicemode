"""Unified service management tool for voice mode services."""

import asyncio
import logging
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Literal, Optional, Dict, Any, Union

import psutil

from voice_mode.server import mcp
from voice_mode.config import WHISPER_PORT, KOKORO_PORT, SERVICE_AUTO_ENABLE
from voice_mode.utils.services.common import find_process_by_port, check_service_status

# Default port for VoiceMode serve command (HTTP MCP server)
VOICEMODE_SERVE_PORT = 8765
from voice_mode.utils.services.whisper_helpers import find_whisper_server, find_whisper_model
from voice_mode.utils.services.kokoro_helpers import find_kokoro_fastapi, has_gpu_support, is_kokoro_starting_up

logger = logging.getLogger("voicemode")


def get_service_config_vars(service_name: str) -> Dict[str, Any]:
    """Get configuration variables for service templates.

    Returns minimal vars needed by simplified templates:
    - HOME: For paths that need absolute paths (macOS plist only)
    - START_SCRIPT: Path to the service start script
    - Service-specific binaries/dirs as needed

    Config like ports/models is now handled by start scripts via voicemode.env
    """
    voicemode_dir = os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    home = os.path.expanduser("~")

    if service_name == "whisper":
        # Find whisper start script
        whisper_dir = os.path.join(voicemode_dir, "services", "whisper")
        start_script = os.path.join(whisper_dir, "bin", "start-whisper-server.sh")

        return {
            "HOME": home,
            "START_SCRIPT": start_script,
        }
    elif service_name == "kokoro":
        kokoro_dir = find_kokoro_fastapi()
        if not kokoro_dir:
            kokoro_dir = os.path.join(voicemode_dir, "services", "kokoro")

        # Find start script
        start_script = None
        if platform.system() == "Darwin":
            start_script = Path(kokoro_dir) / "start-gpu_mac.sh"
        else:
            # On Linux, prefer GPU script if GPU is available, otherwise use CPU script
            if has_gpu_support():
                possible_scripts = [
                    Path(kokoro_dir) / "start-gpu.sh",
                    Path(kokoro_dir) / "start-cpu.sh"
                ]
            else:
                possible_scripts = [
                    Path(kokoro_dir) / "start-cpu.sh",
                    Path(kokoro_dir) / "start-gpu.sh"
                ]

            for script in possible_scripts:
                if script.exists():
                    start_script = script
                    break

        from voice_mode.config import KOKORO_MAX_REQUESTS

        return {
            "HOME": home,
            "START_SCRIPT": str(start_script) if start_script and start_script.exists() else "",
            "KOKORO_DIR": kokoro_dir,
            "KOKORO_MAX_REQUESTS": str(KOKORO_MAX_REQUESTS),
        }
    elif service_name == "voicemode":
        # VoiceMode serve service - runs the HTTP MCP server
        start_script = os.path.join(voicemode_dir, "services", "voicemode", "bin", "start-voicemode-serve.sh")

        return {
            "HOME": home,
            "START_SCRIPT": start_script,
        }
    elif service_name == "connect":
        # VoiceMode connect service - runs voicemode connect up for remote voice
        start_script = os.path.join(voicemode_dir, "services", "connect", "bin", "start-voicemode-connect.sh")

        return {
            "HOME": home,
            "START_SCRIPT": start_script,
        }
    else:
        raise ValueError(f"Unknown service: {service_name}")


async def install_voicemode_start_script() -> Dict[str, Any]:
    """Install the VoiceMode start script to the expected location.

    Unlike whisper/kokoro which require compilation, voicemode is built into
    the package. This function copies the start script template to the
    ~/.voicemode/services/voicemode/bin/ directory.

    Returns:
        Dict with success status and start_script path
    """
    voicemode_dir = os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    bin_dir = os.path.join(voicemode_dir, "services", "voicemode", "bin")
    start_script_path = os.path.join(bin_dir, "start-voicemode-serve.sh")

    try:
        # Create bin directory if it doesn't exist
        os.makedirs(bin_dir, exist_ok=True)

        # Load template script from package
        template_path = Path(__file__).parent.parent / "templates" / "scripts" / "start-voicemode-serve.sh"
        if not template_path.exists():
            return {"success": False, "error": f"Template not found: {template_path}"}

        template_content = template_path.read_text()

        # Write the start script
        with open(start_script_path, 'w') as f:
            f.write(template_content)

        # Make executable
        os.chmod(start_script_path, 0o755)

        logger.info(f"Installed VoiceMode start script at {start_script_path}")
        return {"success": True, "start_script": start_script_path}

    except Exception as e:
        logger.error(f"Error installing VoiceMode start script: {e}")
        return {"success": False, "error": str(e)}


async def install_voicemode_connect_script() -> Dict[str, Any]:
    """Install the VoiceMode Connect start script to the expected location.

    Similar to install_voicemode_start_script() but for the connect service.
    This function copies the start script template to the
    ~/.voicemode/services/connect/bin/ directory.

    Returns:
        Dict with success status and start_script path
    """
    voicemode_dir = os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    bin_dir = os.path.join(voicemode_dir, "services", "connect", "bin")
    start_script_path = os.path.join(bin_dir, "start-voicemode-connect.sh")

    try:
        # Create bin directory if it doesn't exist
        os.makedirs(bin_dir, exist_ok=True)

        # Load template script from package
        template_path = Path(__file__).parent.parent / "templates" / "scripts" / "start-voicemode-connect.sh"
        if not template_path.exists():
            return {"success": False, "error": f"Template not found: {template_path}"}

        template_content = template_path.read_text()

        # Write the start script
        with open(start_script_path, 'w') as f:
            f.write(template_content)

        # Make executable
        os.chmod(start_script_path, 0o755)

        logger.info(f"Installed VoiceMode Connect start script at {start_script_path}")
        return {"success": True, "start_script": start_script_path}

    except Exception as e:
        logger.error(f"Error installing VoiceMode Connect start script: {e}")
        return {"success": False, "error": str(e)}


def find_connect_process():
    """Find the voicemode connect up process by command line.

    Unlike other services that listen on ports, connect is a WebSocket client.
    We find it by looking for the voicemode connect up command.

    Returns:
        psutil.Process if found, None otherwise
    """
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            # Join cmdline to search for the pattern
            cmdline_str = ' '.join(cmdline).lower()
            if 'voicemode' in cmdline_str and 'connect' in cmdline_str and 'up' in cmdline_str:
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def load_service_template(service_name: str) -> str:
    """Load service file template from templates."""
    system = platform.system()
    templates_dir = Path(__file__).parent.parent / "templates"

    # Map service name to template name (voicemode uses "serve" in template names)
    # connect uses "connect" directly (no mapping needed)
    template_name = "serve" if service_name == "voicemode" else service_name

    if system == "Darwin":
        template_path = templates_dir / "launchd" / f"com.voicemode.{template_name}.plist"
    else:
        template_path = templates_dir / "systemd" / f"voicemode-{template_name}.service"

    if not template_path.exists():
        raise FileNotFoundError(f"Service template not found: {template_path}")

    return template_path.read_text()


def create_service_file(service_name: str) -> tuple[Path, str]:
    """Create service file content from template with config vars.

    This is the single source of truth for generating service files.
    Templates are simplified - start scripts handle config via voicemode.env.

    Args:
        service_name: Name of the service (whisper, kokoro, voicemode)

    Returns:
        Tuple of (destination_path, file_content)
    """
    system = platform.system()
    home = os.path.expanduser("~")

    # Load template
    template = load_service_template(service_name)

    # Get config variables
    config_vars = get_service_config_vars(service_name)

    # Format template with config vars
    content = template.format(**config_vars)

    # Map service name to file name (voicemode uses "serve" in file names)
    # connect uses "connect" directly (no mapping needed)
    file_name = "serve" if service_name == "voicemode" else service_name

    # Determine destination path
    if system == "Darwin":
        dest_path = Path(home) / "Library" / "LaunchAgents" / f"com.voicemode.{file_name}.plist"
    else:
        dest_path = Path(home) / ".config" / "systemd" / "user" / f"voicemode-{file_name}.service"

    # Ensure log directory exists (voicemode uses 'serve' for logs, connect uses 'connect')
    log_dir = Path(home) / ".voicemode" / "logs" / file_name
    log_dir.mkdir(parents=True, exist_ok=True)

    return dest_path, content


async def status_service(service_name: str) -> str:
    """Get status of a service."""
    # Connect service is special - it's a WebSocket client, not a port listener
    if service_name == "connect":
        parts = []

        # Standalone connect up process
        proc = find_connect_process()
        if proc:
            # Build process status (reuses the logic below for proc info)
            try:
                with proc.oneshot():
                    cpu_percent = proc.cpu_percent(interval=0.1)
                    memory_info = proc.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024
                    create_time = proc.create_time()

                uptime_seconds = time.time() - create_time
                hours = int(uptime_seconds // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                seconds = int(uptime_seconds % 60)
                if hours > 0:
                    uptime_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    uptime_str = f"{minutes}m {seconds}s"
                else:
                    uptime_str = f"{seconds}s"

                parts.append(f"""✅ Connect process is running
   PID: {proc.pid}
   CPU: {cpu_percent:.1f}%
   Memory: {memory_mb:.1f} MB
   Uptime: {uptime_str}
   Type: WebSocket client""")
            except Exception:
                parts.append(f"Connect process is running (PID: {proc.pid}) but could not get details")

        # In-process WebSocket client (voicemode.dev)
        from voice_mode.connect.client import get_client
        client = get_client()
        if not client.is_connected and not client.is_connecting:
            await client.connect()
        parts.append(client.get_status_text())

        if not parts:
            return "❌ Connect is not available (no credentials - run: voicemode connect login)"
        return "\n\n".join(parts)
    else:
        if service_name == "whisper":
            port = WHISPER_PORT
            process_name = "whisper-server"
        elif service_name == "kokoro":
            port = KOKORO_PORT
            process_name = None
        elif service_name == "voicemode":
            port = VOICEMODE_SERVE_PORT
            process_name = None
        else:
            port = 3000
            process_name = None

        status, proc = check_service_status(port, process_name=process_name)

        if status == "initializing":
            return f"⏳ {service_name.capitalize()} is initializing (process running, waiting for server to be ready)"
        elif status == "not_available":
            # For Kokoro, check if it's in the process of starting up
            if service_name == "kokoro":
                startup_status = is_kokoro_starting_up()
                if startup_status:
                    return f"⏳ Kokoro is {startup_status}"
            return f"❌ {service_name.capitalize()} is not available"
        elif status == "forwarded":
            return f"""🔄 {service_name.capitalize()} is available via port forwarding
   Port: {port} (forwarded)
   Local process: Not running
   Remote: Accessible"""
    
    try:
        with proc.oneshot():
            cpu_percent = proc.cpu_percent(interval=0.1)
            memory_info = proc.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            create_time = proc.create_time()
            cmdline = proc.cmdline()
        
        # Calculate uptime
        uptime_seconds = time.time() - create_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        
        if hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"
        
        # Service-specific info
        extra_info_parts = []
        
        if service_name == "whisper":
            # Get model info
            model = "unknown"
            model_name = None
            for i, arg in enumerate(cmdline):
                if arg == "--model" and i + 1 < len(cmdline):
                    model = Path(cmdline[i + 1]).name
                    # Extract model name from filename (e.g., ggml-large-v3-turbo.bin -> large-v3-turbo)
                    if model.startswith("ggml-") and model.endswith(".bin"):
                        model_name = model[5:-4]
                    break
            extra_info_parts.append(f"Model: {model}")
            
            # Get version and capability info
            try:
                from voice_mode.utils.services.whisper_version import get_whisper_version_info, check_coreml_model_exists
                version_info = get_whisper_version_info()
                
                if version_info.get("version"):
                    extra_info_parts.append(f"Version: {version_info['version']}")
                elif version_info.get("commit"):
                    extra_info_parts.append(f"Commit: {version_info['commit']}")
                
                # Show Core ML status on Apple Silicon
                if platform.machine() == "arm64" and platform.system() == "Darwin":
                    if version_info.get("coreml_supported"):
                        # Check if the current model has Core ML
                        if model_name and check_coreml_model_exists(model_name):
                            extra_info_parts.append("Core ML: ✓ Enabled & Active")
                        else:
                            extra_info_parts.append("Core ML: ✓ Supported (model not converted)")
                    else:
                        extra_info_parts.append("Core ML: ✗ Not compiled in")
                
                # Show GPU support
                gpu_support = []
                if version_info.get("metal_supported"):
                    gpu_support.append("Metal")
                if version_info.get("cuda_supported"):
                    gpu_support.append("CUDA")
                if gpu_support:
                    extra_info_parts.append(f"GPU: {', '.join(gpu_support)}")
            except:
                pass
                
        elif service_name == "kokoro":
            # Try to get version info
            try:
                from voice_mode.utils.services.version_info import get_kokoro_version
                version_info = get_kokoro_version()
                if version_info.get("api_version"):
                    extra_info_parts.append(f"API Version: {version_info['api_version']}")
                elif version_info.get("version"):
                    extra_info_parts.append(f"Version: {version_info['version']}")
            except:
                pass
        elif service_name == "voicemode":
            # VoiceMode HTTP server info
            # Extract transport and host from command line
            transport = "streamable-http"  # default
            host = "127.0.0.1"  # default
            for i, arg in enumerate(cmdline):
                if arg == "--transport" and i + 1 < len(cmdline):
                    transport = cmdline[i + 1]
                elif arg == "--host" and i + 1 < len(cmdline):
                    host = cmdline[i + 1]
            extra_info_parts.append(f"Transport: {transport}")
            extra_info_parts.append(f"Host: {host}")
            # Try to get version info
            try:
                from voice_mode.version import __version__
                extra_info_parts.append(f"Version: {__version__}")
            except:
                pass
        elif service_name == "connect":
            # VoiceMode Connect info (WebSocket client, no port)
            extra_info_parts.append("Type: WebSocket client")
            # Try to get version info
            try:
                from voice_mode.version import __version__
                extra_info_parts.append(f"Version: {__version__}")
            except:
                pass

        extra_info = ""
        if extra_info_parts:
            extra_info = "\n   " + "\n   ".join(extra_info_parts)

        # Build output - connect doesn't have a port
        port_line = f"\n   Port: {port}" if port is not None else ""

        return f"""✅ {service_name.capitalize()} is running locally
   PID: {proc.pid}{port_line}
   CPU: {cpu_percent:.1f}%
   Memory: {memory_mb:.1f} MB
   Uptime: {uptime_str}{extra_info}"""
        
    except Exception as e:
        logger.error(f"Error getting process info: {e}")
        return f"{service_name.capitalize()} is running (PID: {proc.pid}) but could not get details"


async def start_service(service_name: str) -> str:
    """Start a service."""
    # Check if already running - connect uses process detection, others use port
    if service_name == "connect":
        if find_connect_process():
            return "Connect is already running"
        port = None
    else:
        if service_name == "whisper":
            port = WHISPER_PORT
        elif service_name == "kokoro":
            port = KOKORO_PORT
        elif service_name == "voicemode":
            port = VOICEMODE_SERVE_PORT
        else:
            port = 3000
        if find_process_by_port(port):
            return f"{service_name.capitalize()} is already running on port {port}"

    system = platform.system()

    # Map service name to file name (voicemode uses "serve" in file names)
    # connect uses "connect" directly
    file_name = "serve" if service_name == "voicemode" else service_name

    # Helper to check if service is running
    def is_service_running():
        if service_name == "connect":
            return find_connect_process() is not None
        return find_process_by_port(port) is not None

    # Check if managed by service manager
    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{file_name}.plist"
        if plist_path.exists():
            # Use launchctl load
            result = subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Wait for service to start
                for _ in range(10):
                    if is_service_running():
                        return f"✅ {service_name.capitalize()} started"
                    await asyncio.sleep(0.5)
                if service_name == "connect":
                    return f"⚠️ {service_name.capitalize()} loaded but not yet detected as running"
                return f"⚠️ {service_name.capitalize()} loaded but not yet listening on port {port}"
            else:
                error = result.stderr or result.stdout
                if "already loaded" in error.lower():
                    # Service is loaded but maybe not running - try to start it
                    # This can happen if the service crashed
                    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.voicemode.{file_name}"], capture_output=True)
                    await asyncio.sleep(2)
                    if is_service_running():
                        return f"✅ {service_name.capitalize()} restarted"
                    return f"⚠️ {service_name.capitalize()} is loaded but failed to start"
                return f"❌ Failed to start {service_name}: {error}"

    elif system == "Linux":
        service_unit = f"voicemode-{file_name}.service"
        service_file = Path.home() / ".config" / "systemd" / "user" / service_unit
        if service_file.exists():
            # Use systemctl start
            result = subprocess.run(
                ["systemctl", "--user", "start", service_unit],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Wait for service to start
                for _ in range(10):
                    if is_service_running():
                        return f"✅ {service_name.capitalize()} started"
                    await asyncio.sleep(0.5)
                if service_name == "connect":
                    return f"⚠️ {service_name.capitalize()} started but not yet detected as running"
                return f"⚠️ {service_name.capitalize()} started but not yet listening on port {port}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to start {service_name}: {error}"
    
    # Fallback to direct process start
    config_vars = get_service_config_vars(service_name)
    if service_name == "whisper":
        # Find whisper-server binary
        whisper_bin = find_whisper_server()
        if not whisper_bin:
            return "❌ whisper-server not found. Please run whisper_install first."
        
        # Find model
        model_file = find_whisper_model()
        if not model_file:
            return "❌ No Whisper model found. Please run download_model first."
        
        # Start whisper-server
        start_script = Path(config_vars["START_SCRIPT"])
        if start_script.exists():
            # Prefer start script if available
            cmd = [str(start_script)]
        else:
            # Fallback to direct binary execution
            cmd = [str(whisper_bin), "--host", "0.0.0.0", "--port", str(port),
                "--model", str(model_file),
                "--inference-path", "/v1/audio/transcriptions",
                "--convert",
            ]
        
    elif service_name == "kokoro":
        # Find kokoro installation
        kokoro_dir = find_kokoro_fastapi()
        if not kokoro_dir:
            return "❌ kokoro-fastapi not found. Please run kokoro_install first."
        
        # Use appropriate start script
        if platform.system() == "Darwin":
            start_script = Path(kokoro_dir) / "start-gpu_mac.sh"
        else:
            # On Linux, prefer GPU script if GPU is available, otherwise use CPU script
            if has_gpu_support():
                # Try GPU scripts first
                possible_scripts = [
                    Path(kokoro_dir) / "start-gpu.sh",
                    Path(kokoro_dir) / "start-cpu.sh"  # last resort
                ]
            else:
                # No GPU, prefer CPU script
                possible_scripts = [
                    Path(kokoro_dir) / "start-cpu.sh",
                    Path(kokoro_dir) / "start-gpu.sh"  # might work with CPU fallback
                ]
            
            start_script = None
            for script in possible_scripts:
                if script.exists():
                    start_script = script
                    break
        
        if not start_script.exists():
            return f"❌ Start script not found: {start_script}"

        cmd = [str(start_script)]

    elif service_name == "voicemode":
        # Start voicemode serve command directly
        # Use sys.executable to ensure we use the same Python that's running this script
        import sys
        cmd = [sys.executable, "-m", "voice_mode", "serve", "--port", str(port)]

    elif service_name == "connect":
        # Start voicemode connect up directly
        import sys
        cmd = [sys.executable, "-m", "voice_mode", "connect", "up"]

    else:
        return f"❌ Unknown service: {service_name}"

    try:
        # Start the process
        cwd = None
        if service_name == "kokoro":
            cwd = Path(kokoro_dir)

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd
        )

        # Wait a moment to check if it started
        await asyncio.sleep(2)

        if process.poll() is not None:
            # Process exited
            stderr = process.stderr.read().decode() if process.stderr else ""
            return f"❌ {service_name.capitalize()} failed to start: {stderr}"

        # Verify it's running - connect uses process detection, others use port
        if service_name == "connect":
            if find_connect_process():
                return f"✅ {service_name.capitalize()} started successfully (PID: {process.pid})"
            else:
                return f"⚠️ {service_name.capitalize()} process started but not yet detected as running"
        else:
            if find_process_by_port(port):
                return f"✅ {service_name.capitalize()} started successfully (PID: {process.pid})"
            else:
                return f"⚠️ {service_name.capitalize()} process started but not listening on port {port} yet"
            
    except Exception as e:
        logger.error(f"Error starting {service_name}: {e}")
        return f"❌ Error starting {service_name}: {str(e)}"


async def stop_service(service_name: str) -> str:
    """Stop a service."""
    # Connect uses process detection, others use port
    if service_name == "connect":
        port = None
    elif service_name == "whisper":
        port = WHISPER_PORT
    elif service_name == "kokoro":
        port = KOKORO_PORT
    elif service_name == "voicemode":
        port = VOICEMODE_SERVE_PORT
    else:
        port = 3000
    system = platform.system()

    # Map service name to file name (voicemode uses "serve" in file names)
    # connect uses "connect" directly
    file_name = "serve" if service_name == "voicemode" else service_name

    # Check if managed by service manager
    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{file_name}.plist"
        if plist_path.exists():
            # Use launchctl unload (without -w to preserve enable state)
            result = subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} stopped"
            else:
                error = result.stderr or result.stdout
                # If service is not loaded, that's ok - it's already stopped
                if "could not find specified service" in error.lower():
                    return f"{service_name.capitalize()} is not running"
                return f"❌ Failed to stop {service_name}: {error}"

    elif system == "Linux":
        service_unit = f"voicemode-{file_name}.service"
        service_file = Path.home() / ".config" / "systemd" / "user" / service_unit
        if service_file.exists():
            # Use systemctl stop
            result = subprocess.run(
                ["systemctl", "--user", "stop", service_unit],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} stopped"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to stop {service_name}: {error}"

    # Fallback to process termination - connect uses process detection
    if service_name == "connect":
        proc = find_connect_process()
    else:
        proc = find_process_by_port(port)
    if not proc:
        return f"{service_name.capitalize()} is not running"
    
    try:
        pid = proc.pid
        proc.terminate()
        
        # Wait for graceful shutdown
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            # Force kill if needed
            proc.kill()
            proc.wait(timeout=5)
        
        return f"✅ {service_name.capitalize()} stopped (was PID: {pid})"
        
    except Exception as e:
        logger.error(f"Error stopping {service_name}: {e}")
        return f"❌ Error stopping {service_name}: {str(e)}"


async def restart_service(service_name: str) -> str:
    """Restart a service."""
    stop_result = await stop_service(service_name)
    
    # Brief pause between stop and start
    await asyncio.sleep(1)
    
    start_result = await start_service(service_name)
    
    return f"Restart {service_name}:\n{stop_result}\n{start_result}"


async def enable_service(service_name: str) -> str:
    """Enable a service to start at boot/login.

    Uses create_service_file() as single source of truth for service file generation.
    """
    system = platform.system()

    try:
        # Create service file using the unified function
        service_path, content = create_service_file(service_name)

        # Validate required components exist
        config_vars = get_service_config_vars(service_name)

        if service_name == "whisper":
            start_script = config_vars.get("START_SCRIPT", "")
            if not start_script or not Path(start_script).exists():
                return "❌ Whisper start script not found. Please run whisper_install first."

        elif service_name == "kokoro":
            start_script = config_vars.get("START_SCRIPT", "")
            if not start_script or not Path(start_script).exists():
                return "❌ Kokoro start script not found. Please run kokoro_install first."

        elif service_name == "voicemode":
            start_script = config_vars.get("START_SCRIPT", "")
            if not start_script or not Path(start_script).exists():
                # Auto-install the start script for voicemode since it's built-in
                install_result = await install_voicemode_start_script()
                if not install_result.get("success"):
                    return f"❌ Failed to install VoiceMode start script: {install_result.get('error', 'Unknown error')}"
                start_script = install_result.get("start_script", "")
                logger.info(f"Auto-installed VoiceMode start script at {start_script}")

        elif service_name == "connect":
            # Validate OAuth credentials exist before enabling connect service
            credentials_file = Path.home() / ".voicemode" / "credentials"
            if not credentials_file.exists():
                return "❌ No credentials found. Run 'voicemode connect login' first to authenticate."

            start_script = config_vars.get("START_SCRIPT", "")
            if not start_script or not Path(start_script).exists():
                # Auto-install the start script for connect since it's built-in
                install_result = await install_voicemode_connect_script()
                if not install_result.get("success"):
                    return f"❌ Failed to install VoiceMode Connect start script: {install_result.get('error', 'Unknown error')}"
                start_script = install_result.get("start_script", "")
                logger.info(f"Auto-installed VoiceMode Connect start script at {start_script}")

        # Create parent directories
        service_path.parent.mkdir(parents=True, exist_ok=True)

        # Write service file
        service_path.write_text(content)

        if system == "Darwin":
            # Load with launchctl
            result = subprocess.run(
                ["launchctl", "load", "-w", str(service_path)],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} service enabled. It will start automatically at login.\nPlist: {service_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable {service_name} service: {error}"

        else:  # Linux
            # Map service name to file name (voicemode uses "serve" in file names)
            file_name = "serve" if service_name == "voicemode" else service_name
            service_unit = f"voicemode-{file_name}.service"

            # Reload and enable systemd
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            result = subprocess.run(
                ["systemctl", "--user", "enable", service_unit],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Also start it now
                subprocess.run(["systemctl", "--user", "start", service_unit], check=True)
                return f"✅ {service_name.capitalize()} service enabled and started.\nService: {service_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable {service_name} service: {error}"

    except Exception as e:
        logger.error(f"Error enabling {service_name} service: {e}")
        return f"❌ Error enabling {service_name} service: {str(e)}"


async def disable_service(service_name: str) -> str:
    """Disable a service from starting at boot/login."""
    system = platform.system()

    # Map service name to file name (voicemode uses "serve" in file names)
    file_name = "serve" if service_name == "voicemode" else service_name

    try:
        if system == "Darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{file_name}.plist"

            if not plist_path.exists():
                return f"{service_name.capitalize()} service is not installed"

            # Unload with launchctl
            result = subprocess.run(
                ["launchctl", "unload", "-w", str(plist_path)],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Remove the plist file
                plist_path.unlink()
                return f"✅ {service_name.capitalize()} service disabled and removed"
            else:
                error = result.stderr or result.stdout
                # If already unloaded, just remove the file
                if "Could not find specified service" in error:
                    plist_path.unlink()
                    return f"✅ {service_name.capitalize()} service was already disabled, plist removed"
                return f"❌ Failed to disable {service_name} service: {error}"

        else:  # Linux
            service_unit = f"voicemode-{file_name}.service"

            # Stop and disable
            subprocess.run(["systemctl", "--user", "stop", service_unit], check=True)
            result = subprocess.run(
                ["systemctl", "--user", "disable", service_unit],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Remove service file
                service_path = Path.home() / ".config" / "systemd" / "user" / service_unit
                if service_path.exists():
                    service_path.unlink()

                # Reload systemd
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)

                return f"✅ {service_name.capitalize()} service disabled and removed"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to disable {service_name} service: {error}"
                
    except Exception as e:
        logger.error(f"Error disabling {service_name} service: {e}")
        return f"❌ Error disabling {service_name} service: {str(e)}"


async def view_logs(service_name: str, lines: Optional[int] = None) -> str:
    """View service logs."""
    system = platform.system()
    lines = lines or 50

    # Map service name to file/log name (voicemode uses "serve" in file names)
    # connect uses "connect" directly
    log_name = "serve" if service_name == "voicemode" else service_name

    try:
        if system == "Darwin":
            # Use log show command
            if service_name == "voicemode":
                process_name = "voicemode-serve"
            elif service_name == "connect":
                process_name = "voicemode"  # connect runs as "voicemode connect up"
            else:
                process_name = f"{service_name}-server"
            cmd = [
                "log", "show",
                "--predicate", f'process == "{process_name}" OR process == "kokoro-fastapi"',
                "--last", f"{lines}",
                "--style", "compact"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0 and result.stdout.strip():
                return f"=== Last {lines} log entries for {service_name} ===\n{result.stdout}"
            else:
                # Fallback to log files (voicemode logs to serve/ directory)
                log_dir = Path.home() / ".voicemode" / "logs" / log_name
                out_log = log_dir / f"{log_name}.out.log"
                err_log = log_dir / f"{log_name}.err.log"

                logs = []
                if out_log.exists():
                    with open(out_log) as f:
                        stdout_lines = f.readlines()[-lines:]
                        if stdout_lines:
                            logs.append(f"=== stdout (last {len(stdout_lines)} lines) ===")
                            logs.extend(stdout_lines)

                if err_log.exists():
                    with open(err_log) as f:
                        stderr_lines = f.readlines()[-lines:]
                        if stderr_lines:
                            if logs:
                                logs.append("")
                            logs.append(f"=== stderr (last {len(stderr_lines)} lines) ===")
                            logs.extend(stderr_lines)

                if logs:
                    return "".join(logs).rstrip()
                else:
                    return f"No logs found for {service_name}"

        else:  # Linux
            # Use journalctl
            cmd = [
                "journalctl", "--user",
                "-u", f"voicemode-{log_name}.service",
                "-n", str(lines),
                "--no-pager"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return f"=== Last {lines} journal entries for {service_name} ===\n{result.stdout}"
            else:
                return f"Failed to retrieve logs: {result.stderr}"
                
    except Exception as e:
        logger.error(f"Error viewing logs for {service_name}: {e}")
        return f"❌ Error viewing logs: {str(e)}"


@mcp.tool()
async def service(
    service_name: Literal["whisper", "kokoro", "voicemode", "connect"],
    action: Literal["status", "start", "stop", "restart", "enable", "disable", "logs"] = "status",
    lines: Optional[Union[int, str]] = None
) -> str:
    """Unified service management tool for voice mode services.

    Manage Whisper (STT), Kokoro (TTS), VoiceMode (HTTP MCP server), and Connect services.

    Args:
        service_name: The service to manage ("whisper", "kokoro", "voicemode", or "connect")
        action: The action to perform (default: "status")
            - status: Show if service is running and resource usage
            - start: Start the service
            - stop: Stop the service
            - restart: Stop and start the service
            - enable: Configure service to start at boot/login
            - disable: Remove service from boot/login
            - logs: View recent service logs
        lines: Number of log lines to show (only for logs action, default: 50)

    Returns:
        Status message indicating the result of the action

    Examples:
        service("whisper", "status")  # Check if Whisper is running
        service("kokoro", "start")    # Start Kokoro service
        service("voicemode", "start") # Start VoiceMode HTTP MCP server
        service("connect", "enable")  # Enable Connect service for remote voice
        service("whisper", "logs", 100)  # View last 100 lines of Whisper logs
    """
    # Convert lines to integer if provided as string
    if lines is not None and isinstance(lines, str):
        try:
            lines = int(lines)
        except ValueError:
            logger.warning(f"Invalid lines value '{lines}', using default 50")
            lines = 50
    
    # Route to appropriate handler
    if action == "status":
        return await status_service(service_name)
    elif action == "start":
        return await start_service(service_name)
    elif action == "stop":
        return await stop_service(service_name)
    elif action == "restart":
        return await restart_service(service_name)
    elif action == "enable":
        return await enable_service(service_name)
    elif action == "disable":
        return await disable_service(service_name)
    elif action == "logs":
        return await view_logs(service_name, lines)
    else:
        return f"❌ Unknown action: {action}"


async def install_service(service_name: str) -> Dict[str, Any]:
    """Install service files for a service."""
    try:
        system = platform.system()
        config_vars = get_service_config_vars(service_name)

        # Load template
        template_content = load_service_template(service_name)

        # Replace placeholders
        for key, value in config_vars.items():
            template_content = template_content.replace(f"{{{key}}}", str(value))

        # Map service name to file name (voicemode uses "serve" in file names)
        file_name = "serve" if service_name == "voicemode" else service_name

        if system == "Darwin":
            # Install launchd plist
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{file_name}.plist"
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            plist_path.write_text(template_content)
            return {"success": True, "service_file": str(plist_path)}
        else:
            # Install systemd service
            service_path = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{file_name}.service"
            service_path.parent.mkdir(parents=True, exist_ok=True)
            service_path.write_text(template_content)

            # Reload systemd
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
            return {"success": True, "service_file": str(service_path)}

    except Exception as e:
        logger.error(f"Error installing service {service_name}: {e}")
        return {"success": False, "error": str(e)}


async def uninstall_service(service_name: str) -> Dict[str, Any]:
    """Remove service files for a service."""
    try:
        system = platform.system()

        # Map service name to file name (voicemode uses "serve" in file names)
        file_name = "serve" if service_name == "voicemode" else service_name

        if system == "Darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{file_name}.plist"
            if plist_path.exists():
                plist_path.unlink()
                return {"success": True, "message": f"Removed {plist_path}"}
            else:
                return {"success": True, "message": "Service file not found"}
        else:
            service_path = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{file_name}.service"
            if service_path.exists():
                service_path.unlink()
                # Reload systemd
                subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
                return {"success": True, "message": f"Removed {service_path}"}
            else:
                return {"success": True, "message": "Service file not found"}

    except Exception as e:
        logger.error(f"Error uninstalling service {service_name}: {e}")
        return {"success": False, "error": str(e)}
