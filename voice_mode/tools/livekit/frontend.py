"""LiveKit Voice Assistant Frontend management."""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from voice_mode.server import mcp

logger = logging.getLogger("voice-mode")

# Global production server instance
_production_server = None


async def start_production_server(frontend_dir: Path, port: int, host: str) -> Dict[str, Any]:
    """Start the production server for built frontend."""
    global _production_server
    
    try:
        # Import here to avoid issues if the module doesn't exist
        from .production_server import ProductionFrontendServer
        
        # Ensure LiveKit environment variables are set with defaults from config
        from voice_mode import config
        os.environ.setdefault("LIVEKIT_URL", config.LIVEKIT_URL)
        os.environ.setdefault("LIVEKIT_API_KEY", config.LIVEKIT_API_KEY)
        os.environ.setdefault("LIVEKIT_API_SECRET", config.LIVEKIT_API_SECRET)
        os.environ.setdefault("LIVEKIT_ACCESS_PASSWORD", "voicemode123")
        
        # Stop any existing server
        if _production_server:
            _production_server.stop()
        
        # Start new server
        _production_server = ProductionFrontendServer(frontend_dir, port, host)
        result = _production_server.start()
        
        if result["success"]:
            # Get password from env file
            env_file = frontend_dir / ".env.local"
            password = "voicemode123"  # default
            if env_file.exists():
                with open(env_file) as f:
                    for line in f:
                        if line.startswith("LIVEKIT_ACCESS_PASSWORD="):
                            password = line.strip().split("=", 1)[1]
                            break
            
            result.update({
                "message": f"Production frontend started on {result['url']}",
                "password": password,
                "directory": str(frontend_dir),
                "mode": result.get("mode", "production")
            })
        
        return result
        
    except ImportError as e:
        logger.error(f"Failed to import production server: {e}")
        return {
            "success": False,
            "error": "Production server not available. Using development fallback."
        }
    except Exception as e:
        logger.error(f"Error starting production server: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def stop_production_server():
    """Stop the production server if running."""
    global _production_server
    
    if _production_server:
        _production_server.stop()
        _production_server = None


def find_frontend_dir() -> Optional[Path]:
    """Find the voice-assistant-frontend directory."""
    # Primary: Use bundled frontend in Python package
    try:
        import voice_mode
        package_dir = Path(voice_mode.__file__).parent
        bundled_frontend = package_dir / "frontend"
        if bundled_frontend.exists() and (bundled_frontend / "package.json").exists():
            return bundled_frontend
    except:
        pass
    
    # Fallback: Check common development/external locations
    voicemode_base = os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
    
    possible_paths = [
        # Vendor directory (development location)
        Path.home() / "Code" / "github.com" / "mbailey" / "voicemode" / "vendor" / "livekit-voice-assistant" / "voice-assistant-frontend",
        # Service directory
        Path(voicemode_base) / "services" / "livekit-frontend", 
        # Development location
        Path.home() / "Code" / "voice-assistant-frontend",
    ]
    
    for path in possible_paths:
        if path.exists() and (path / "package.json").exists():
            return path
    
    return None


@mcp.tool()
async def livekit_frontend_start(
    port: int = None,
    host: str = None
) -> Dict[str, Any]:
    """Start the LiveKit voice assistant frontend.
    
    Starts the Next.js frontend application for voice conversations with LiveKit.
    
    Args:
        port: Port to run the frontend on (default: uses VOICEMODE_FRONTEND_PORT or 3000)
        host: Host to bind to (default: uses VOICEMODE_FRONTEND_HOST or 127.0.0.1)
    
    Returns:
        Dictionary with start status and access URL
    """
    try:
        # Import config to get defaults
        from voice_mode import config
        
        # Use config defaults if not provided
        if port is None:
            port = config.FRONTEND_PORT
        if host is None:
            host = config.FRONTEND_HOST
        # Find frontend directory
        frontend_dir = find_frontend_dir()
        if not frontend_dir:
            return {
                "success": False,
                "error": "Voice assistant frontend not found. Please install it first."
            }
        
        # Check if already running
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                return {
                    "success": False,
                    "error": f"Port {port} is already in use. Frontend may already be running."
                }
        except:
            pass
        
        # Check if dependencies are installed and try to install if needed
        node_modules = frontend_dir / "node_modules"
        if not node_modules.exists() or not (node_modules / ".bin" / "next").exists():
            logger.info("Installing frontend dependencies...")
            
            # Try different package managers
            install_commands = [
                ["pnpm", "install"],
                ["npm", "install"],
                ["yarn", "install"]
            ]
            
            installed = False
            last_error = None
            
            for cmd in install_commands:
                try:
                    logger.info(f"Trying to install dependencies with: {' '.join(cmd)}")
                    result = subprocess.run(
                        cmd,
                        cwd=frontend_dir,
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    logger.info(f"Dependencies installed successfully with {cmd[0]}")
                    installed = True
                    break
                except subprocess.CalledProcessError as e:
                    last_error = f"{cmd[0]}: {e.stderr}"
                    logger.warning(f"Failed with {cmd[0]}: {e.stderr}")
                except FileNotFoundError:
                    last_error = f"{cmd[0]} not found"
                    logger.warning(f"{cmd[0]} not found, trying next...")
                    continue
            
            if not installed:
                return {
                    "success": False,
                    "error": f"Failed to install dependencies. Last error: {last_error}"
                }
        
        # Check if we have a production build and should use it
        build_dir = frontend_dir / ".next"
        use_production = (
            build_dir.exists() and 
            os.environ.get("FRONTEND_MODE", "auto") in ("production", "auto")
        )
        
        if use_production:
            logger.info("Using production build (found .next directory)")
            return await start_production_server(frontend_dir, port, host)
        
        # Start the development server
        logger.info("Using development server")
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["HOST"] = host
        
        # Ensure LiveKit environment variables are set with defaults from config
        from voice_mode import config
        env.setdefault("LIVEKIT_URL", config.LIVEKIT_URL)
        env.setdefault("LIVEKIT_API_KEY", config.LIVEKIT_API_KEY)
        env.setdefault("LIVEKIT_API_SECRET", config.LIVEKIT_API_SECRET)
        env.setdefault("LIVEKIT_ACCESS_PASSWORD", "voicemode123")
        
        # Try pnpm dev first, fallback to npx if pnpm isn't available
        start_commands = [
            ["pnpm", "dev"],
            ["npx", "next", "dev"],
            ["npm", "run", "dev"]
        ]
        
        process = None
        last_error = None
        
        # Create log directory
        log_dir = Path.home() / ".voicemode" / "logs" / "frontend"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "frontend.log"
        
        for cmd in start_commands:
            try:
                logger.info(f"Trying to start frontend with: {' '.join(cmd)}")
                
                # Open log file for writing
                with open(log_file, "a") as log:
                    log.write(f"\n=== {' '.join(cmd)} started at {datetime.now()} ===\n")
                    log.flush()
                    
                    process = subprocess.Popen(
                        cmd,
                        cwd=frontend_dir,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT
                    )
                
                # Test if it started successfully - wait longer and check port
                await asyncio.sleep(3)
                if process.poll() is None:
                    # Check if port is actually in use
                    port_check = subprocess.run(
                        ["lsof", "-ti", f":{port}"],
                        capture_output=True,
                        text=True
                    )
                    if port_check.stdout.strip():
                        logger.info(f"Frontend started successfully with: {' '.join(cmd)} on port {port}")
                        break
                    else:
                        logger.warning(f"Process running but port {port} not bound")
                        process.terminate()
                        process = None
                        last_error = f"Port {port} not bound after startup"
                else:
                    last_error = f"Process exited with code {process.returncode}"
                    logger.warning(f"Command {' '.join(cmd)} failed: {last_error}")
                    process = None
            except Exception as e:
                logger.warning(f"Failed to start with {' '.join(cmd)}: {e}")
                last_error = str(e)
                continue
        
        if process is None:
            return {
                "success": False,
                "error": f"Failed to start frontend with any command. Last error: {last_error}"
            }
        
        # Wait a moment to check if it started (already checked above)
        await asyncio.sleep(2)
        
        # Get .env.local settings
        env_file = frontend_dir / ".env.local"
        password = "voicemode123"  # default
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith("LIVEKIT_ACCESS_PASSWORD="):
                        password = line.strip().split("=", 1)[1]
        
        return {
            "success": True,
            "message": f"Frontend started successfully",
            "url": f"http://{host}:{port}",
            "password": password,
            "pid": process.pid,
            "directory": str(frontend_dir)
        }
        
    except Exception as e:
        logger.error(f"Error starting frontend: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def livekit_frontend_stop() -> Dict[str, Any]:
    """Stop the LiveKit voice assistant frontend.
    
    Stops any running instance of the voice assistant frontend.
    
    Returns:
        Dictionary with stop status
    """
    try:
        # First try to stop production server if running
        global _production_server
        production_stopped = False
        
        if _production_server and _production_server.is_running():
            stop_production_server()
            production_stopped = True
            logger.info("Stopped production frontend server")
        
        # Also check for development servers on port 3000
        result = subprocess.run(
            ["lsof", "-ti", ":3000"],
            capture_output=True,
            text=True
        )
        
        dev_stopped = False
        if result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                try:
                    subprocess.run(["kill", "-TERM", pid], check=True)
                except:
                    pass
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Force kill if still running
            for pid in pids:
                try:
                    subprocess.run(["kill", "-9", pid], check=True)
                except:
                    pass
            
            dev_stopped = True
            logger.info(f"Stopped development frontend processes: {', '.join(pids)}")
        
        if production_stopped and dev_stopped:
            message = "Frontend stopped (both production and development servers)"
        elif production_stopped:
            message = "Frontend stopped (production server)"
        elif dev_stopped:
            message = f"Frontend stopped (development processes)"
        else:
            message = "Frontend was not running"
        
        return {
            "success": True,
            "message": message
        }
            
    except Exception as e:
        logger.error(f"Error stopping frontend: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def livekit_frontend_status() -> Dict[str, Any]:
    """Check status of the LiveKit voice assistant frontend.
    
    Returns:
        Dictionary with frontend status and configuration
    """
    try:
        # Check if running
        result = subprocess.run(
            ["lsof", "-ti", ":3000"],
            capture_output=True,
            text=True
        )
        
        is_running = bool(result.stdout.strip())
        pid = result.stdout.strip() if is_running else None
        
        # Find frontend directory
        frontend_dir = find_frontend_dir()
        if not frontend_dir:
            return {
                "running": False,
                "error": "Frontend directory not found"
            }
        
        # Check configuration
        env_file = frontend_dir / ".env.local"
        config = {}
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        # Don't expose secrets
                        if "SECRET" not in key:
                            config[key] = value
        
        return {
            "running": is_running,
            "pid": pid,
            "directory": str(frontend_dir),
            "url": "http://127.0.0.1:3000" if is_running else None,
            "configuration": config
        }
        
    except Exception as e:
        logger.error(f"Error checking frontend status: {e}")
        return {"error": str(e)}


@mcp.tool()
async def livekit_frontend_open() -> Dict[str, Any]:
    """Open the LiveKit voice assistant frontend in the default browser.
    
    Starts the frontend if not already running, then opens it in the browser.
    
    Returns:
        Dictionary with status and URL
    """
    try:
        # Check if frontend is running
        status = await livekit_frontend_status.fn()
        
        if not status.get("running"):
            # Start the frontend first
            logger.info("Frontend not running, starting it first...")
            start_result = await livekit_frontend_start.fn()
            if not start_result.get("success"):
                return {
                    "success": False,
                    "error": f"Failed to start frontend: {start_result.get('error', 'Unknown error')}"
                }
            url = start_result.get("url", "http://127.0.0.1:3000")
            password = start_result.get("password", "Check .env.local")
            
            # Wait a moment for it to fully start
            await asyncio.sleep(3)
        else:
            url = status.get("url", "http://127.0.0.1:3000")
            # Get password from env file
            frontend_dir = find_frontend_dir()
            password = "voicemode123"  # default
            if frontend_dir:
                env_file = frontend_dir / ".env.local"
                if env_file.exists():
                    with open(env_file) as f:
                        for line in f:
                            if line.startswith("LIVEKIT_ACCESS_PASSWORD="):
                                password = line.strip().split("=", 1)[1]
                                break
        
        # Open in browser
        import webbrowser
        import platform
        
        system = platform.system()
        if system == "Darwin":
            # macOS
            subprocess.run(["open", url])
        elif system == "Linux":
            # Linux - try xdg-open first, then fallback to webbrowser
            try:
                subprocess.run(["xdg-open", url], check=True)
            except:
                webbrowser.open(url)
        else:
            # Windows or other
            webbrowser.open(url)
        
        return {
            "success": True,
            "message": f"Opened frontend in browser",
            "url": url,
            "password": password,
            "hint": "Use the password to access the voice assistant interface"
        }
        
    except Exception as e:
        logger.error(f"Error opening frontend: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def livekit_frontend_logs(
    lines: int = 50,
    follow: bool = False
) -> Dict[str, Any]:
    """View LiveKit voice assistant frontend logs.
    
    Args:
        lines: Number of lines to show (default: 50)
        follow: Whether to follow/tail the logs (default: False)
    
    Returns:
        Dictionary with log content and location
    """
    try:
        log_dir = Path.home() / ".voicemode" / "logs" / "frontend"
        log_file = log_dir / "frontend.log"
        
        if not log_file.exists():
            return {
                "success": False,
                "error": "No frontend logs found. Start the frontend first to generate logs.",
                "log_file": str(log_file)
            }
        
        if follow:
            # For tailing logs, we return the command to run
            return {
                "success": True,
                "message": f"Use this command to tail logs:",
                "command": f"tail -f {log_file}",
                "log_file": str(log_file)
            }
        else:
            # Read the last N lines
            try:
                result = subprocess.run(
                    ["tail", "-n", str(lines), str(log_file)],
                    capture_output=True,
                    text=True
                )
                return {
                    "success": True,
                    "logs": result.stdout,
                    "log_file": str(log_file),
                    "lines_shown": lines
                }
            except Exception as e:
                # Fallback to reading with Python
                with open(log_file, 'r') as f:
                    all_lines = f.readlines()
                    last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                    return {
                        "success": True,
                        "logs": ''.join(last_lines),
                        "log_file": str(log_file),
                        "lines_shown": len(last_lines)
                    }
        
    except Exception as e:
        logger.error(f"Error reading frontend logs: {e}")
        return {"success": False, "error": str(e)}


@mcp.tool()
async def livekit_frontend_install(
    auto_enable: Optional[bool] = None
) -> Dict[str, Any]:
    """Install and setup LiveKit Voice Assistant Frontend.
    
    Since the frontend is bundled with Voice Mode, this mainly handles
    service setup and auto-enabling functionality.
    
    Args:
        auto_enable: Enable service after setup. If None, uses VOICEMODE_SERVICE_AUTO_ENABLE config.
    
    Returns:
        Dictionary with installation status and configuration details
    """
    try:
        # Import config for auto-enable default
        from voice_mode.config import SERVICE_AUTO_ENABLE
        
        # Handle string boolean conversions  
        if isinstance(auto_enable, str):
            auto_enable = auto_enable.lower() in ("true", "1", "yes", "on")
        
        # Determine auto_enable default
        if auto_enable is None:
            auto_enable = SERVICE_AUTO_ENABLE
        
        # Find frontend directory
        frontend_dir = find_frontend_dir()
        if not frontend_dir:
            return {
                "success": False,
                "error": "Frontend directory not found. Frontend should be bundled with Voice Mode."
            }
        
        # Check if Node.js is available (for development/local installs)
        node_available = False
        node_path = None
        
        # Enhanced Node.js detection for macOS
        possible_node_paths = [
            "/opt/homebrew/bin/node",      # Apple Silicon Homebrew
            "/usr/local/bin/node",         # Intel Homebrew / Linux
            "/usr/bin/node",              # System Node
            "/opt/local/bin/node",        # MacPorts
        ]
        
        for path in possible_node_paths:
            if Path(path).exists() and os.access(path, os.X_OK):
                node_available = True
                node_path = path
                logger.info(f"Found Node.js at: {path}")
                break
        
        if not node_available:
            logger.warning("Node.js not found - frontend will require production build for service mode")
        
        # Install dependencies if Node.js is available and this looks like a development install
        package_json = frontend_dir / "package.json"
        node_modules = frontend_dir / "node_modules"
        
        if node_available and package_json.exists() and not node_modules.exists():
            logger.info("Installing frontend dependencies...")
            try:
                # Try different package managers
                install_commands = [
                    ["pnpm", "install"],
                    ["npm", "install"], 
                    ["yarn", "install"]
                ]
                
                installed = False
                for cmd in install_commands:
                    try:
                        subprocess.run(
                            cmd,
                            cwd=frontend_dir,
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        logger.info(f"Dependencies installed with {cmd[0]}")
                        installed = True
                        break
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        continue
                
                if not installed:
                    logger.warning("Could not install dependencies with any package manager")
                    
            except Exception as e:
                logger.warning(f"Failed to install frontend dependencies: {e}")
        
        # Create log directory
        voicemode_dir = os.path.expanduser(os.environ.get("VOICEMODE_BASE_DIR", "~/.voicemode"))
        log_dir = Path(voicemode_dir) / "logs" / "frontend"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Install service files
        from voice_mode.tools.service import install_service, enable_service
        
        service_result = await install_service("frontend")
        if not service_result["success"]:
            logger.warning(f"Frontend service installation failed: {service_result.get('error', 'Unknown error')}")
        
        # Enable service if requested
        service_enabled = False
        if auto_enable and service_result["success"]:
            enable_result = await enable_service("frontend")
            # enable_service returns a string message, not a dict
            if isinstance(enable_result, str) and "✅" in enable_result:
                service_enabled = True
                logger.info(f"Frontend service auto-enabled: {enable_result}")
            else:
                logger.warning(f"Frontend service enable failed: {enable_result}")
        
        return {
            "success": True,
            "frontend_dir": str(frontend_dir),
            "log_dir": str(log_dir),
            "node_available": node_available,
            "node_path": node_path,
            "dependencies_installed": node_modules.exists() if package_json.exists() else None,
            "service_installed": service_result["success"],
            "service_enabled": service_enabled,
            "auto_enable": auto_enable,
            "url": "http://localhost:3000",
            "password": "voicemode123"
        }
        
    except Exception as e:
        logger.error(f"Error installing frontend: {e}")
        return {"success": False, "error": str(e)}