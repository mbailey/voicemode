#!/usr/bin/env python3
"""
Test script to reproduce rapid converse calls that might trigger BrokenResourceError.

This script simulates the scenario where multiple converse tool calls are made
in quick succession, which can cause stdio pipe issues.
"""

import asyncio
import json
import sys
from typing import Dict, Any


class MCPTestClient:
    """Simple MCP client simulator for testing"""
    
    def __init__(self):
        self.request_id = 0
    
    async def send_request(self, method: str, params: Dict[str, Any]) -> None:
        """Send a JSON-RPC request to the MCP server via stdout"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }
        print(json.dumps(request))
        sys.stdout.flush()
    
    async def call_converse(self, message: str, wait_for_response: bool = True, duration: float = 20.0):
        """Call the converse tool"""
        await self.send_request("tools/call", {
            "name": "converse",
            "arguments": {
                "message": message,
                "wait_for_response": wait_for_response,
                "listen_duration_max": duration
            }
        })


async def test_rapid_calls():
    """Test rapid converse calls"""
    client = MCPTestClient()
    
    print("Starting rapid converse call test...", file=sys.stderr)
    
    # Scenario 1: Call while previous is still processing
    print("\nScenario 1: Overlapping calls", file=sys.stderr)
    await client.call_converse("First message", wait_for_response=True, duration=20.0)
    await asyncio.sleep(0.5)  # Short delay while first is still processing
    await client.call_converse("Second message", wait_for_response=False)
    
    # Scenario 2: Very rapid successive calls
    print("\nScenario 2: Rapid successive calls", file=sys.stderr)
    await asyncio.sleep(25)  # Wait for first to complete
    for i in range(3):
        await client.call_converse(f"Rapid message {i}", wait_for_response=False)
        await asyncio.sleep(0.1)  # Very short delay
    
    # Scenario 3: Mixed wait/no-wait calls
    print("\nScenario 3: Mixed wait/no-wait calls", file=sys.stderr)
    await asyncio.sleep(5)
    await client.call_converse("Listen for response", wait_for_response=True, duration=10.0)
    await asyncio.sleep(2)  # Interrupt during listening
    await client.call_converse("Interrupt message", wait_for_response=False)
    
    print("\nTest completed", file=sys.stderr)


if __name__ == "__main__":
    print("""
This test script simulates rapid MCP tool calls.
To use it, run the voice-mode server with debug logging:

    export VOICE_MODE_DEBUG=trace
    python test_rapid_converse.py | voice-mode

Watch for BrokenResourceError or similar issues.
""", file=sys.stderr)
    
    asyncio.run(test_rapid_calls())