"""Common utilities for service management tools."""

import psutil
from typing import Optional
import logging

logger = logging.getLogger("voice-mode")


def find_process_by_port(port: int) -> Optional[psutil.Process]:
    """Find a process listening on the specified port."""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        logger.error(f"Error finding process by port: {e}")
    return None