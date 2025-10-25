"""Dependency checking tools for audio system diagnostics."""

import logging
from typing import Dict, Any

from voice_mode.server import mcp
from voice_mode.utils.audio_diagnostics import (
    check_system_audio_packages,
    check_pulseaudio_status,
    diagnose_audio_setup
)

logger = logging.getLogger("voicemode")


@mcp.tool()
async def check_audio_dependencies() -> Dict[str, Any]:
    """Check system audio dependencies and provide installation guidance.
    
    This tool checks for required system packages, PulseAudio status,
    and Python audio libraries. It provides specific installation commands
    for missing dependencies based on your platform.
    
    Useful when:
    - Voice mode fails with audio errors
    - Setting up on a new system
    - Troubleshooting WSL audio issues
    
    Returns:
        Dictionary containing:
        - platform: System platform (Linux, macOS, Windows)
        - packages: Status of system packages (Linux only)
        - missing_packages: List of packages that need installation
        - install_command: Command to install missing packages
        - pulseaudio: PulseAudio status (Linux only)
        - diagnostics: List of diagnostic findings
        - recommendations: Specific recommendations for your setup
    """
    try:
        import platform
        import os
        
        result = {
            "platform": platform.system(),
            "platform_details": platform.platform(),
            "diagnostics": diagnose_audio_setup()
        }
        
        # Check if WSL
        is_wsl = False
        if result["platform"] == "Linux" and os.path.exists("/proc/version"):
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower() or "wsl" in f.read().lower():
                    is_wsl = True
                    result["environment"] = "WSL"
        
        # Linux-specific checks
        if result["platform"] == "Linux":
            # Check packages
            packages = check_system_audio_packages()
            result["packages"] = packages
            
            missing = [pkg for pkg, installed in packages.items() if not installed]
            result["missing_packages"] = missing
            
            if missing:
                result["install_command"] = f"sudo apt update && sudo apt install -y {' '.join(missing)}"
            
            # Check PulseAudio
            pa_running, pa_status = check_pulseaudio_status()
            result["pulseaudio"] = {
                "running": pa_running,
                "status": pa_status
            }
        
        # Check Python audio
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            input_devices = [d for d in devices if d['max_input_channels'] > 0]
            
            result["python_audio"] = {
                "sounddevice_installed": True,
                "total_devices": len(devices),
                "input_devices": len(input_devices),
                "device_list": [
                    f"{i}: {d['name']} (in:{d['max_input_channels']}, out:{d['max_output_channels']})"
                    for i, d in enumerate(devices)
                ]
            }
        except Exception as e:
            result["python_audio"] = {
                "sounddevice_installed": False,
                "error": str(e)
            }
        
        # Generate recommendations
        recommendations = []
        
        if result["platform"] == "Linux":
            if result.get("missing_packages"):
                recommendations.append(f"Install missing packages: {result['install_command']}")
            
            if not result.get("pulseaudio", {}).get("running"):
                recommendations.append("Start PulseAudio: pulseaudio --start")
            
            if is_wsl:
                recommendations.append("Check Windows microphone permissions: Settings → Privacy → Microphone")
                recommendations.append("See docs/troubleshooting/wsl2-microphone-access.md for detailed WSL setup")
        
        if not result.get("python_audio", {}).get("sounddevice_installed"):
            recommendations.append("Install Python audio libraries: pip install sounddevice numpy scipy")
        elif result.get("python_audio", {}).get("input_devices", 0) == 0:
            recommendations.append("No input devices found. Check microphone connection and permissions.")
            if is_wsl:
                recommendations.append("Consider using LiveKit transport instead of local microphone")
        
        result["recommendations"] = recommendations
        
        # Format as readable text
        output = [
            f"=== Audio Dependency Check ===",
            f"Platform: {result['platform']} ({result.get('environment', 'Native')})",
            ""
        ]
        
        if result["platform"] == "Linux":
            output.append("System Packages:")
            for pkg, installed in result.get("packages", {}).items():
                status = "✓" if installed else "✗"
                output.append(f"  {status} {pkg}")
            output.append("")
            
            if result.get("missing_packages"):
                output.append(f"Install missing packages:")
                output.append(f"  {result['install_command']}")
                output.append("")
            
            pa = result.get("pulseaudio", {})
            output.append(f"PulseAudio: {'✓ Running' if pa.get('running') else '✗ Not running'}")
            output.append(f"  {pa.get('status', '')}")
            output.append("")
        
        audio = result.get("python_audio", {})
        if audio.get("sounddevice_installed"):
            output.append(f"Python Audio: ✓ sounddevice installed")
            output.append(f"  Devices: {audio.get('total_devices', 0)} total, {audio.get('input_devices', 0)} input")
        else:
            output.append(f"Python Audio: ✗ sounddevice not working")
            output.append(f"  Error: {audio.get('error', 'Unknown')}")
        output.append("")
        
        if recommendations:
            output.append("Recommendations:")
            for rec in recommendations:
                output.append(f"  • {rec}")
        else:
            output.append("✓ All dependencies appear to be satisfied")
        
        return {
            "text": "\n".join(output),
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error checking dependencies: {e}")
        return {
            "text": f"Error checking dependencies: {e}",
            "data": {"error": str(e)}
        }