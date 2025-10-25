"""Common utilities for service management tools."""

import psutil
import socket
from typing import Optional, Tuple
import logging

logger = logging.getLogger("voicemode")


def find_process_by_port(port: int) -> Optional[psutil.Process]:
    """Find a process listening on the specified port.
    
    Returns None if port is only accessible via SSH forwarding or other non-local means.
    """
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Skip if we can't access process info (might be another user's process)
                if not proc.is_running():
                    continue
                
                # Skip SSH processes - these are port forwards, not actual services
                proc_name = proc.name().lower()
                if proc_name in ['ssh', 'sshd']:
                    continue
                    
                for conn in proc.net_connections():
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        # Verify this is a real local process
                        try:
                            # Try to access basic process info to ensure it's real
                            _ = proc.pid
                            _ = proc.create_time()
                            return proc
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # Process doesn't actually exist or we can't access it
                            continue
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        logger.error(f"Error finding process by port: {e}")
    return None


def is_port_accessible(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    """Check if a port is accessible (can connect to it).
    
    This will return True for both locally running services and SSH-forwarded ports.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            return result == 0
    except Exception as e:
        logger.error(f"Error checking port accessibility: {e}")
        return False


def check_service_status(port: int) -> Tuple[str, Optional[psutil.Process]]:
    """Check the status of a service on a given port.
    
    Returns:
        Tuple of (status, process):
        - ("local", process) if running locally
        - ("forwarded", None) if accessible but not local
        - ("not_available", None) if not accessible at all
    """
    # First check if there's a local process
    proc = find_process_by_port(port)
    if proc:
        return ("local", proc)
    
    # No local process, check if port is accessible (might be forwarded)
    if is_port_accessible(port):
        return ("forwarded", None)
    
    # Not accessible at all
    return ("not_available", None)