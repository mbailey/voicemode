"""Unified service management tool for voice mode services."""

import asyncio
import json
import logging
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Literal, Optional, Dict, Any

import psutil

from voice_mode.server import mcp
from voice_mode.config import WHISPER_PORT, KOKORO_PORT, SERVICE_AUTO_ENABLE
from voice_mode.utils.services.common import find_process_by_port
from voice_mode.utils.services.whisper_helpers import find_whisper_server, find_whisper_model
from voice_mode.utils.services.kokoro_helpers import find_kokoro_fastapi

logger = logging.getLogger("voice-mode")


def load_service_file_version(service_name: str, file_type: str) -> Optional[str]:
    """Load version information for a service file."""
    versions_file = Path(__file__).parent.parent / "resources" / "versions.json"
    if not versions_file.exists():
        return None
    
    try:
        with open(versions_file) as f:
            versions = json.load(f)
        
        if file_type == "plist":
            filename = f"com.voicemode.{service_name}.plist"
        else:  # systemd
            filename = f"voicemode-{service_name}.service"
        
        return versions.get("service_files", {}).get(filename)
    except Exception as e:
        logger.error(f"Error loading versions: {e}")
        return None


def get_installed_service_version(service_name: str) -> Optional[str]:
    """Get the version of an installed service file."""
    system = platform.system()
    
    if system == "Darwin":
        file_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
    else:
        file_path = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{service_name}.service"
    
    if not file_path.exists():
        return None
    
    try:
        content = file_path.read_text()
        # Extract version from comment
        for line in content.split('\n'):
            if 'v' in line and ('<!--' in line or '#' in line):
                # Extract version number
                import re
                match = re.search(r'v(\d+\.\d+\.\d+)', line)
                if match:
                    return match.group(1)
    except Exception as e:
        logger.debug(f"Could not read version from {file_path}: {e}")
    
    return None


def load_service_template(service_name: str) -> str:
    """Load service file template from resources."""
    system = platform.system()
    resources_dir = Path(__file__).parent.parent / "resources"
    
    if system == "Darwin":
        template_path = resources_dir / "launchd" / f"com.voicemode.{service_name}.plist"
    else:
        template_path = resources_dir / "systemd" / f"voicemode-{service_name}.service"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Service template not found: {template_path}")
    
    return template_path.read_text()


async def status_service(service_name: str) -> str:
    """Get status of a service."""
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    proc = find_process_by_port(port)
    
    if not proc:
        return f"{service_name.capitalize()} is not running on port {port}"
    
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
            for i, arg in enumerate(cmdline):
                if arg == "--model" and i + 1 < len(cmdline):
                    model = Path(cmdline[i + 1]).name
                    break
            extra_info_parts.append(f"Model: {model}")
            
            # Try to get version info
            try:
                from voice_mode.tools.services.version_info import get_whisper_version
                version_info = get_whisper_version()
                if version_info.get("version"):
                    extra_info_parts.append(f"Version: {version_info['version']}")
            except:
                pass
                
        else:  # kokoro
            # Try to get version info
            try:
                from voice_mode.tools.services.version_info import get_kokoro_version
                version_info = get_kokoro_version()
                if version_info.get("api_version"):
                    extra_info_parts.append(f"API Version: {version_info['api_version']}")
                elif version_info.get("version"):
                    extra_info_parts.append(f"Version: {version_info['version']}")
            except:
                pass
        
        extra_info = ""
        if extra_info_parts:
            extra_info = "\n   " + "\n   ".join(extra_info_parts)
        
        return f"""✅ {service_name.capitalize()} is running
   PID: {proc.pid}
   Port: {port}
   CPU: {cpu_percent:.1f}%
   Memory: {memory_mb:.1f} MB
   Uptime: {uptime_str}{extra_info}"""
        
    except Exception as e:
        logger.error(f"Error getting process info: {e}")
        return f"{service_name.capitalize()} is running (PID: {proc.pid}) but could not get details"


async def start_service(service_name: str) -> str:
    """Start a service."""
    # Check if already running
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    if find_process_by_port(port):
        return f"{service_name.capitalize()} is already running on port {port}"
    
    system = platform.system()
    
    # Check if managed by service manager
    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
        if plist_path.exists():
            # Use launchctl load
            result = subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Wait for service to start
                for i in range(10):
                    if find_process_by_port(port):
                        return f"✅ {service_name.capitalize()} started"
                    await asyncio.sleep(0.5)
                return f"⚠️ {service_name.capitalize()} loaded but not yet listening on port {port}"
            else:
                error = result.stderr or result.stdout
                if "already loaded" in error.lower():
                    # Service is loaded but maybe not running - try to start it
                    # This can happen if the service crashed
                    subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/com.voicemode.{service_name}"], capture_output=True)
                    await asyncio.sleep(2)
                    if find_process_by_port(port):
                        return f"✅ {service_name.capitalize()} restarted"
                    return f"⚠️ {service_name.capitalize()} is loaded but failed to start"
                return f"❌ Failed to start {service_name}: {error}"
    
    elif system == "Linux":
        service_file = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{service_name}.service"
        if service_file.exists():
            # Use systemctl start
            result = subprocess.run(
                ["systemctl", "--user", "start", f"voicemode-{service_name}.service"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Wait for service to start
                for i in range(10):
                    if find_process_by_port(port):
                        return f"✅ {service_name.capitalize()} started"
                    await asyncio.sleep(0.5)
                return f"⚠️ {service_name.capitalize()} started but not yet listening on port {port}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to start {service_name}: {error}"
    
    # Fallback to direct process start
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
        cmd = [str(whisper_bin), "--host", "0.0.0.0", "--port", str(port), "--model", str(model_file)]
        
    else:  # kokoro
        # Find kokoro installation
        kokoro_dir = find_kokoro_fastapi()
        if not kokoro_dir:
            return "❌ kokoro-fastapi not found. Please run kokoro_install first."
        
        # Use appropriate start script
        if platform.system() == "Darwin":
            start_script = Path(kokoro_dir) / "start-gpu_mac.sh"
        else:
            start_script = Path(kokoro_dir) / "start.sh"
        
        if not start_script.exists():
            return f"❌ Start script not found: {start_script}"
        
        cmd = [str(start_script)]
    
    try:
        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(kokoro_dir) if service_name == "kokoro" else None
        )
        
        # Wait a moment to check if it started
        await asyncio.sleep(2)
        
        if process.poll() is not None:
            # Process exited
            stderr = process.stderr.read().decode() if process.stderr else ""
            return f"❌ {service_name.capitalize()} failed to start: {stderr}"
        
        # Verify it's listening
        if find_process_by_port(port):
            return f"✅ {service_name.capitalize()} started successfully (PID: {process.pid})"
        else:
            return f"⚠️ {service_name.capitalize()} process started but not listening on port {port} yet"
            
    except Exception as e:
        logger.error(f"Error starting {service_name}: {e}")
        return f"❌ Error starting {service_name}: {str(e)}"


async def stop_service(service_name: str) -> str:
    """Stop a service."""
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    system = platform.system()
    
    # Check if managed by service manager
    if system == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
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
        service_file = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{service_name}.service"
        if service_file.exists():
            # Use systemctl stop
            result = subprocess.run(
                ["systemctl", "--user", "stop", f"voicemode-{service_name}.service"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} stopped"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to stop {service_name}: {error}"
    
    # Fallback to process termination
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
    """Enable a service to start at boot/login."""
    system = platform.system()
    
    # Check version and offer update if needed
    installed_version = get_installed_service_version(service_name)
    current_version = load_service_file_version(service_name, "plist" if system == "Darwin" else "service")
    
    if installed_version and current_version and installed_version != current_version:
        logger.info(f"Service file update available: {installed_version} -> {current_version}")
    
    try:
        if system == "Darwin":
            # Load template
            template = load_service_template(service_name)
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
            logs_dir = Path.home() / ".voicemode" / "logs"
            
            # Prepare substitutions
            if service_name == "whisper":
                whisper_bin = find_whisper_server()
                if not whisper_bin:
                    return "❌ whisper-server not found. Please run whisper_install first."
                
                model_file = find_whisper_model()
                if not model_file:
                    return "❌ No Whisper model found. Please run download_model first."
                
                content = template.format(
                    WHISPER_BIN=whisper_bin,
                    WHISPER_PORT=WHISPER_PORT,
                    MODEL_FILE=model_file,
                    LOG_DIR=logs_dir,
                    WORKING_DIR=Path(whisper_bin).parent
                )
            else:  # kokoro
                kokoro_dir = find_kokoro_fastapi()
                if not kokoro_dir:
                    return "❌ kokoro-fastapi not found. Please run kokoro_install first."
                
                start_script = Path(kokoro_dir) / "start-gpu_mac.sh"
                if not start_script.exists():
                    return f"❌ Start script not found: {start_script}"
                
                content = template.format(
                    START_SCRIPT=start_script,
                    KOKORO_DIR=kokoro_dir,
                    KOKORO_PORT=KOKORO_PORT,
                    LOG_DIR=logs_dir
                )
            
            # Create directories
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Write plist
            plist_path.write_text(content)
            
            # Load with launchctl
            result = subprocess.run(
                ["launchctl", "load", "-w", str(plist_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} service enabled. It will start automatically at login.\nPlist: {plist_path}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to enable {service_name} service: {error}"
                
        else:  # Linux
            # Load template
            template = load_service_template(service_name)
            service_path = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{service_name}.service"
            
            # Prepare substitutions
            if service_name == "whisper":
                whisper_bin = find_whisper_server()
                if not whisper_bin:
                    return "❌ whisper-server not found. Please run whisper_install first."
                
                model_file = find_whisper_model()
                if not model_file:
                    return "❌ No Whisper model found. Please run download_model first."
                
                content = template.format(
                    WHISPER_BIN=whisper_bin,
                    WHISPER_PORT=WHISPER_PORT,
                    MODEL_FILE=model_file,
                    WORKING_DIR=Path(whisper_bin).parent
                )
            else:  # kokoro
                kokoro_dir = find_kokoro_fastapi()
                if not kokoro_dir:
                    return "❌ kokoro-fastapi not found. Please run kokoro_install first."
                
                start_script = Path(kokoro_dir) / "start.sh"
                if not start_script.exists():
                    return f"❌ Start script not found: {start_script}"
                
                content = template.format(
                    START_SCRIPT=start_script,
                    KOKORO_DIR=kokoro_dir,
                    KOKORO_PORT=KOKORO_PORT
                )
            
            # Write service file
            service_path.parent.mkdir(parents=True, exist_ok=True)
            service_path.write_text(content)
            
            # Reload and enable
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            result = subprocess.run(
                ["systemctl", "--user", "enable", f"voicemode-{service_name}.service"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Also start it now
                subprocess.run(["systemctl", "--user", "start", f"voicemode-{service_name}.service"], check=True)
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
    
    try:
        if system == "Darwin":
            plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
            
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
            service_name_full = f"voicemode-{service_name}.service"
            
            # Stop and disable
            subprocess.run(["systemctl", "--user", "stop", service_name_full], check=True)
            result = subprocess.run(
                ["systemctl", "--user", "disable", service_name_full],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                # Remove service file
                service_path = Path.home() / ".config" / "systemd" / "user" / service_name_full
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
    
    try:
        if system == "Darwin":
            # Use log show command
            cmd = [
                "log", "show",
                "--predicate", f'process == "{service_name}-server" OR process == "kokoro-fastapi"',
                "--last", f"{lines}",
                "--style", "compact"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                return f"=== Last {lines} log entries for {service_name} ===\n{result.stdout}"
            else:
                # Fallback to log files
                log_dir = Path.home() / ".voicemode" / "logs"
                out_log = log_dir / f"{service_name}.out.log"
                err_log = log_dir / f"{service_name}.err.log"
                
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
                "-u", f"voicemode-{service_name}.service",
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
    service_name: Literal["whisper", "kokoro"],
    action: Literal["status", "start", "stop", "restart", "enable", "disable", "logs"] = "status",
    lines: Optional[int] = None
) -> str:
    """Unified service management tool for voice mode services.
    
    Manage Whisper (STT) and Kokoro (TTS) services with a single tool.
    
    Args:
        service_name: The service to manage ("whisper" or "kokoro")
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
        service("whisper", "logs", 100)  # View last 100 lines of Whisper logs
    """
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