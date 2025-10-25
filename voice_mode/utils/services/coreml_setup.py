"""Setup and manage CoreML Python environment for whisper.cpp."""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("voicemode")


def setup_coreml_venv(whisper_dir: Path, force: bool = False) -> Dict[str, Any]:
    """
    Setup a dedicated Python virtual environment for CoreML conversion.
    
    Uses whisper.cpp's requirements-coreml.txt to ensure compatibility.
    
    Args:
        whisper_dir: Path to whisper.cpp installation
        force: Force recreation of venv even if it exists
        
    Returns:
        Dict with 'success' and 'python_path' or 'error'
    """
    venv_dir = whisper_dir / "venv-coreml"
    venv_python = venv_dir / "bin" / "python"
    requirements_file = whisper_dir / "models" / "requirements-coreml.txt"
    
    # Check if requirements file exists
    if not requirements_file.exists():
        return {
            "success": False,
            "error": f"CoreML requirements file not found at {requirements_file}"
        }
    
    # Check if venv already exists and is valid
    if venv_python.exists() and not force:
        # Test if the venv has the required packages
        try:
            result = subprocess.run(
                [str(venv_python), "-c", "import torch, coremltools, whisper, ane_transformers"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"CoreML venv already exists and is valid at {venv_dir}")
                return {
                    "success": True,
                    "python_path": str(venv_python),
                    "message": "Using existing CoreML virtual environment"
                }
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            logger.info("Existing CoreML venv is incomplete, will recreate")
    
    # Create or recreate venv
    logger.info(f"Creating CoreML virtual environment at {venv_dir}")
    
    try:
        # Remove existing venv if force or invalid
        if venv_dir.exists() and (force or not venv_python.exists()):
            import shutil
            shutil.rmtree(venv_dir, ignore_errors=True)
        
        # Try to use Python 3.11 as recommended by whisper.cpp
        python_cmd = None
        for python_version in ["python3.11", "python3.10", "python3.9", "python3"]:
            if subprocess.run(["which", python_version], capture_output=True).returncode == 0:
                # Check actual version
                version_result = subprocess.run(
                    [python_version, "--version"],
                    capture_output=True,
                    text=True
                )
                if version_result.returncode == 0:
                    version = version_result.stdout.strip()
                    logger.info(f"Found {version}")
                    # Strongly prefer 3.11 as recommended
                    if "3.11" in version:
                        python_cmd = python_version
                        logger.info("Using Python 3.11 (recommended for CoreML)")
                        break
                    elif "3.10" in version or "3.9" in version:
                        if python_cmd is None:  # Use as fallback if no 3.11
                            python_cmd = python_version
                    elif python_cmd is None:
                        python_cmd = python_version  # Use as last resort
        
        if python_cmd is None:
            return {
                "success": False,
                "error": "No suitable Python version found. Python 3.9-3.11 recommended for CoreML."
            }
        
        # Create venv
        logger.info(f"Creating venv with {python_cmd}")
        result = subprocess.run(
            [python_cmd, "-m", "venv", str(venv_dir)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to create venv: {result.stderr}"
            }
        
        # Upgrade pip
        logger.info("Upgrading pip in CoreML venv")
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
            capture_output=True,
            text=True
        )
        
        # Install requirements with proper versions
        # Based on whisper.cpp documentation and coremltools compatibility
        # Python 3.11 is recommended, torch 2.5.0 is known to work with coremltools
        logger.info("Installing CoreML requirements with compatible versions")
        packages = [
            "torch==2.5.0",  # Specific version mentioned in whisper.cpp for coremltools compatibility
            "coremltools>=7.0",
            "openai-whisper",
            "ane_transformers"
        ]
        
        # Try installing all at once first
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install"] + packages,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # Try installing packages one by one if bulk install fails
            logger.warning("Bulk install failed, trying packages individually")
            
            failed_packages = []
            for package in packages:
                logger.info(f"Installing {package}")
                result = subprocess.run(
                    [str(venv_python), "-m", "pip", "install", package],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to install {package}: {result.stderr}")
                    failed_packages.append(package)
            
            if failed_packages:
                return {
                    "success": False,
                    "error": f"Failed to install packages: {', '.join(failed_packages)}",
                    "partial": True,
                    "python_path": str(venv_python)
                }
        
        # Verify installation
        logger.info("Verifying CoreML dependencies")
        result = subprocess.run(
            [str(venv_python), "-c", "import torch, coremltools, whisper, ane_transformers; print('All packages imported successfully')"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("CoreML virtual environment created successfully")
            return {
                "success": True,
                "python_path": str(venv_python),
                "message": "CoreML virtual environment created with all dependencies"
            }
        else:
            return {
                "success": True,  # Partial success
                "python_path": str(venv_python),
                "warning": "Some packages may be missing but environment was created",
                "verification_error": result.stderr
            }
            
    except Exception as e:
        logger.error(f"Error setting up CoreML venv: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_coreml_python(whisper_dir: Path) -> Optional[str]:
    """
    Get the path to Python executable with CoreML dependencies.
    
    Checks in order:
    1. Dedicated venv-coreml environment
    2. Existing venv environment (if it has CoreML packages)
    3. None if no suitable environment found
    
    Args:
        whisper_dir: Path to whisper.cpp installation
        
    Returns:
        Path to Python executable or None
    """
    # Check dedicated CoreML venv first
    venv_coreml_python = whisper_dir / "venv-coreml" / "bin" / "python"
    if venv_coreml_python.exists():
        # Quick check if it has required packages
        try:
            result = subprocess.run(
                [str(venv_coreml_python), "-c", "import torch, coremltools"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return str(venv_coreml_python)
        except:
            pass
    
    # Check existing venv as fallback
    venv_python = whisper_dir / "venv" / "bin" / "python"
    if venv_python.exists():
        try:
            result = subprocess.run(
                [str(venv_python), "-c", "import torch, coremltools, whisper"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return str(venv_python)
        except:
            pass
    
    return None