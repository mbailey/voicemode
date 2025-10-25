"""GPU detection utilities for voice mode."""

import platform
import subprocess
from typing import Tuple, Optional
import logging

logger = logging.getLogger("voicemode")


def detect_gpu() -> Tuple[bool, Optional[str]]:
    """Detect GPU availability and type.
    
    Returns:
        Tuple of (has_gpu, gpu_type) where gpu_type is one of:
        - "metal" for macOS Metal Performance Shaders
        - "cuda" for NVIDIA CUDA
        - "rocm" for AMD ROCm
        - "cpu" or None if no GPU detected
    """
    system = platform.system()
    
    if system == "Darwin":
        # macOS always has Metal support on modern systems
        try:
            # Check if running on Apple Silicon
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                check=True
            )
            cpu_info = result.stdout.strip()
            
            # Apple Silicon (M1, M2, M3, etc.) has excellent GPU
            if any(chip in cpu_info for chip in ["Apple", "M1", "M2", "M3"]):
                return True, "metal"
            
            # Intel Macs might have Metal but less powerful
            # Still return True as Metal is available
            return True, "metal"
        except:
            # Fallback - assume Metal is available on macOS
            return True, "metal"
    
    elif system == "Linux":
        # Check for NVIDIA GPU
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                check=True
            )
            if result.returncode == 0:
                logger.debug("NVIDIA GPU detected")
                return True, "cuda"
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        
        # Check for AMD GPU with ROCm
        try:
            result = subprocess.run(
                ["rocm-smi"],
                capture_output=True,
                check=True
            )
            if result.returncode == 0:
                logger.debug("AMD GPU with ROCm detected")
                return True, "rocm"
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
        
        # Check for any GPU via lspci
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.lower()
            
            # Look for NVIDIA or AMD GPUs
            if "nvidia" in output and ("vga" in output or "3d" in output):
                logger.debug("NVIDIA GPU detected via lspci (CUDA not available)")
                return False, "cpu"  # GPU present but no CUDA
            
            if "amd" in output and ("vga" in output or "3d" in output):
                # Check if it's just integrated graphics
                if "radeon" in output and not any(x in output for x in ["vega", "navi", "rx"]):
                    logger.debug("AMD integrated graphics detected")
                    return False, "cpu"
                logger.debug("AMD GPU detected via lspci (ROCm not available)")
                return False, "cpu"  # GPU present but no ROCm
        except:
            pass
    
    # No GPU detected or unsupported platform
    return False, "cpu"


def has_gpu_support() -> bool:
    """Simple check if GPU is available and usable.
    
    Returns:
        True if a supported GPU is available, False otherwise
    """
    has_gpu, gpu_type = detect_gpu()
    return has_gpu and gpu_type != "cpu"


def get_gpu_type() -> Optional[str]:
    """Get the type of GPU available.
    
    Returns:
        GPU type string ("metal", "cuda", "rocm") or None
    """
    _, gpu_type = detect_gpu()
    return gpu_type if gpu_type != "cpu" else None