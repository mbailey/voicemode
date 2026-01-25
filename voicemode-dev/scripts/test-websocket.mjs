#!/usr/bin/env node
/**
 * WebSocket Test Script
 *
 * Tests the basic Durable Object lifecycle and WebSocket functionality.
 * Run with: npm run test:ws
 *
 * Prerequisites:
 * - Start the dev server: npm run dev
 * - The server should be running on http://localhost:8787
 */

const WS_URL = process.env.WS_URL || "ws://localhost:8787/ws/test-user";

async function runTests() {
  console.log("=== WebSocket Gateway Test ===\n");
  console.log(`Connecting to: ${WS_URL}\n`);

  // Test 1: Health check (HTTP)
  console.log("Test 1: Health check (HTTP)...");
  try {
    const healthUrl = WS_URL.replace("ws://", "http://").replace("/ws/test-user", "/health");
    const response = await fetch(healthUrl);
    const data = await response.json();
    console.log("  Status:", response.status);
    console.log("  Response:", JSON.stringify(data, null, 2));
    console.log("  ✓ Health check passed\n");
  } catch (error) {
    console.log("  ✗ Health check failed:", error.message);
    console.log("  Make sure the dev server is running: npm run dev\n");
    process.exit(1);
  }

  // Test 2: WebSocket connection
  console.log("Test 2: WebSocket connection...");
  const WebSocket = (await import("ws")).default;

  const ws = new WebSocket(WS_URL);

  const results = {
    connected: false,
    heartbeatAck: false,
    pingPong: false,
    echo: false,
  };

  ws.on("open", () => {
    console.log("  ✓ Connected\n");
    results.connected = true;

    // Test 3: Heartbeat
    console.log("Test 3: Heartbeat...");
    ws.send(JSON.stringify({ type: "heartbeat" }));
  });

  ws.on("message", (data) => {
    const msg = JSON.parse(data.toString());
    console.log("  Received:", JSON.stringify(msg));

    if (msg.type === "heartbeat_ack") {
      console.log("  ✓ Heartbeat acknowledged\n");
      results.heartbeatAck = true;

      // Test 4: Ping/Pong
      console.log("Test 4: Ping/Pong...");
      ws.send(JSON.stringify({ type: "ping" }));
    }

    if (msg.type === "pong") {
      console.log("  ✓ Pong received\n");
      results.pingPong = true;

      // Test 5: Echo (unknown message)
      console.log("Test 5: Echo (unknown message type)...");
      ws.send(JSON.stringify({ type: "test_message", data: "hello" }));
    }

    if (msg.type === "echo") {
      console.log("  ✓ Echo received\n");
      results.echo = true;

      // All tests complete
      ws.close(1000, "Tests complete");
    }
  });

  ws.on("error", (error) => {
    console.log("  ✗ WebSocket error:", error.message);
    process.exit(1);
  });

  ws.on("close", (code, reason) => {
    console.log(`Connection closed. Code: ${code}, Reason: ${reason}\n`);

    // Print results
    console.log("=== Test Results ===");
    console.log(`Connected:      ${results.connected ? "✓" : "✗"}`);
    console.log(`Heartbeat:      ${results.heartbeatAck ? "✓" : "✗"}`);
    console.log(`Ping/Pong:      ${results.pingPong ? "✓" : "✗"}`);
    console.log(`Echo:           ${results.echo ? "✓" : "✗"}`);

    const allPassed = Object.values(results).every(Boolean);
    console.log(`\n${allPassed ? "All tests passed! ✓" : "Some tests failed ✗"}`);

    process.exit(allPassed ? 0 : 1);
  });
}

runTests().catch((error) => {
  console.error("Test script error:", error);
  process.exit(1);
});
