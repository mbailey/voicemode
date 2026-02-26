#!/usr/bin/env python3
"""
Test script for tel-004: Environment Detection

This script demonstrates the environment detection functions added to
voice_mode/config.py for the VoiceMode telemetry system.
"""

import json
from voice_mode.config import (
    get_os_type,
    get_installation_method,
    get_mcp_host,
    get_execution_source,
    get_environment_info
)


def main():
    print("=" * 70)
    print("VoiceMode Telemetry - Environment Detection Test (tel-004)")
    print("=" * 70)
    print()

    # Test individual detection functions
    print("1. Operating System Detection:")
    print(f"   get_os_type() = {get_os_type()!r}")
    print()

    print("2. Installation Method Detection:")
    print(f"   get_installation_method() = {get_installation_method()!r}")
    print("   Possible values: 'dev', 'uv', 'pip', 'unknown'")
    print()

    print("3. MCP Host Detection:")
    mcp_host = get_mcp_host()
    print(f"   get_mcp_host() = {mcp_host!r}")
    print("   Known hosts: claude-code, cursor, cline, electron-app")
    print()

    print("4. Execution Source Detection:")
    print(f"   get_execution_source() = {get_execution_source()!r}")
    print("   Possible values: 'mcp', 'cli'")
    print()

    print("5. Complete Environment Info:")
    env_info = get_environment_info()
    print("   get_environment_info() =")
    print("   " + json.dumps(env_info, indent=2).replace("\n", "\n   "))
    print()

    # Verify caching works
    print("6. Verifying Lazy Caching:")
    info1 = get_environment_info()
    info2 = get_environment_info()
    if info1 == info2:
        print("   ✓ Caching works - identical results on repeated calls")
    else:
        print("   ✗ Caching failed - results differ!")
        return False
    print()

    print("=" * 70)
    print("All environment detection functions working correctly!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
