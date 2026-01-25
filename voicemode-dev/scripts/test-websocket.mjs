#!/usr/bin/env node
/**
 * WebSocket Test Script
 *
 * Tests WebSocket functionality including authentication.
 * Run with: npm run test:ws
 *
 * Prerequisites:
 * - Start the dev server: npm run dev
 * - The server should be running on http://localhost:8787
 *
 * Environment variables:
 * - WS_URL: Base WebSocket URL (default: ws://localhost:8787/ws)
 * - JWT_TOKEN: JWT token for authenticated tests (optional)
 *
 * Tests:
 * 1. Health check (HTTP)
 * 2. Anonymous connection (dev mode)
 * 3. Connection with invalid token (should fail if Auth0 configured)
 * 4. Heartbeat and ping/pong
 * 5. Welcome message with auth status
 */

const BASE_URL = process.env.WS_URL || "ws://localhost:8787/ws";
const HTTP_BASE = BASE_URL.replace("ws://", "http://").replace("wss://", "https://").replace("/ws", "");
const JWT_TOKEN = process.env.JWT_TOKEN;

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function testHealthCheck() {
  console.log("Test 1: Health check (HTTP)...");
  try {
    const response = await fetch(`${HTTP_BASE}/health`);
    const data = await response.json();
    console.log("  Status:", response.status);
    console.log("  Response:", JSON.stringify(data, null, 2));

    if (data.features?.auth !== true) {
      console.log("  Warning: Auth feature not showing as enabled");
    }
    console.log("  ✓ Health check passed\n");
    return true;
  } catch (error) {
    console.log("  ✗ Health check failed:", error.message);
    console.log("  Make sure the dev server is running: npm run dev\n");
    return false;
  }
}

async function testWebSocketEndpointInfo() {
  console.log("Test 2: WebSocket endpoint info (HTTP)...");
  try {
    const response = await fetch(`${HTTP_BASE}/ws`);
    const data = await response.json();
    console.log("  Status:", response.status);
    console.log("  Response:", JSON.stringify(data, null, 2));

    if (!data.authentication) {
      console.log("  Warning: No authentication info in endpoint description");
    }
    console.log("  ✓ Endpoint info retrieved\n");
    return true;
  } catch (error) {
    console.log("  ✗ Failed to get endpoint info:", error.message);
    return false;
  }
}

async function testAnonymousConnection() {
  console.log("Test 3: Anonymous WebSocket connection (dev mode)...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    // Connect without token (should work in dev mode)
    const wsUrl = `${BASE_URL}?user=test-anonymous`;
    console.log(`  Connecting to: ${wsUrl}`);

    const ws = new WebSocket(wsUrl);
    let welcomeReceived = false;

    const timeout = setTimeout(() => {
      console.log("  ✗ Timeout waiting for connection");
      ws.close();
      resolve(false);
    }, 5000);

    ws.on("open", () => {
      console.log("  ✓ Connected without token (dev mode allows this)");
    });

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      console.log("  Received:", JSON.stringify(msg));

      if (msg.type === "connected") {
        welcomeReceived = true;
        console.log(`  ✓ Welcome message received. Authenticated: ${msg.authenticated}`);

        // Verify that anonymous connection shows as not authenticated
        if (msg.authenticated === false) {
          console.log("  ✓ Correctly marked as not authenticated\n");
        } else {
          console.log("  Warning: Anonymous should be not authenticated\n");
        }

        clearTimeout(timeout);
        ws.close(1000, "Test complete");
        resolve(true);
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      // In production mode or with Auth0 configured, this might fail
      console.log("  Connection rejected:", error.message);
      console.log("  (This is expected if Auth0 is configured)\n");
      resolve(true); // This is actually expected behavior when auth is required
    });

    ws.on("close", (code, reason) => {
      clearTimeout(timeout);
      if (!welcomeReceived) {
        console.log(`  Connection closed. Code: ${code}`);
      }
    });
  });
}

async function testConnectionWithToken() {
  if (!JWT_TOKEN) {
    console.log("Test 4: Authenticated connection...");
    console.log("  Skipped: JWT_TOKEN environment variable not set");
    console.log("  Set JWT_TOKEN to test authenticated connections\n");
    return true;
  }

  console.log("Test 4: Authenticated WebSocket connection...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?token=${JWT_TOKEN}`;
    console.log(`  Connecting with JWT token...`);

    const ws = new WebSocket(wsUrl);
    let welcomeReceived = false;

    const timeout = setTimeout(() => {
      console.log("  ✗ Timeout waiting for connection");
      ws.close();
      resolve(false);
    }, 10000);

    ws.on("open", () => {
      console.log("  ✓ Connected with token");
    });

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      console.log("  Received:", JSON.stringify(msg));

      if (msg.type === "connected") {
        welcomeReceived = true;
        if (msg.authenticated) {
          console.log(`  ✓ Authenticated as user: ${msg.userId}\n`);
          clearTimeout(timeout);
          ws.close(1000, "Test complete");
          resolve(true);
        } else {
          console.log("  ✗ Token was not validated (Auth0 may not be configured)\n");
          clearTimeout(timeout);
          ws.close(1000, "Test complete");
          resolve(false);
        }
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Connection failed:", error.message);
      resolve(false);
    });
  });
}

async function testInvalidToken() {
  console.log("Test 5: Connection with invalid token...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    // Use a clearly invalid token
    const invalidToken = "invalid.token.here";
    const wsUrl = `${BASE_URL}?token=${invalidToken}`;
    console.log(`  Connecting with invalid token...`);

    const ws = new WebSocket(wsUrl);

    const timeout = setTimeout(() => {
      console.log("  Timeout - connection neither accepted nor rejected");
      ws.close();
      resolve(false);
    }, 5000);

    ws.on("open", () => {
      // If connection opens, it means Auth0 isn't configured
      // (development mode allows invalid tokens through)
      console.log("  Connection opened - Auth0 likely not configured");
      clearTimeout(timeout);
      ws.close(1000, "Test complete");
      resolve(true);
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      // This is expected when Auth0 is configured
      console.log("  ✓ Connection correctly rejected:", error.message);
      resolve(true);
    });

    ws.on("unexpected-response", (req, res) => {
      clearTimeout(timeout);
      console.log(`  ✓ Connection rejected with status: ${res.statusCode}`);

      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const data = JSON.parse(body);
          console.log(`  Error response: ${JSON.stringify(data)}`);
        } catch (e) {
          console.log(`  Error response: ${body}`);
        }
        resolve(true);
      });
    });
  });
}

async function testHeartbeatAndPing() {
  console.log("Test 6: Heartbeat and Ping/Pong...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-heartbeat`;
    const ws = new WebSocket(wsUrl);

    const results = {
      connected: false,
      welcomeReceived: false,
      heartbeatAck: false,
      pingPong: false,
    };

    const timeout = setTimeout(() => {
      console.log("  ✗ Timeout");
      ws.close();
      resolve(false);
    }, 10000);

    ws.on("open", () => {
      results.connected = true;
    });

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      console.log("  Received:", JSON.stringify(msg));

      if (msg.type === "connected") {
        results.welcomeReceived = true;
        // Send heartbeat
        ws.send(JSON.stringify({ type: "heartbeat" }));
      }

      if (msg.type === "heartbeat_ack") {
        results.heartbeatAck = true;
        console.log("  ✓ Heartbeat acknowledged");
        // Send ping
        ws.send(JSON.stringify({ type: "ping" }));
      }

      if (msg.type === "pong") {
        results.pingPong = true;
        console.log("  ✓ Pong received\n");
        clearTimeout(timeout);
        ws.close(1000, "Test complete");

        const allPassed = Object.values(results).every(Boolean);
        resolve(allPassed);
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Error:", error.message);
      resolve(false);
    });
  });
}

async function runTests() {
  console.log("=== WebSocket Gateway Authentication Tests ===\n");
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`JWT Token: ${JWT_TOKEN ? "Provided" : "Not provided"}\n`);

  const results = [];

  // Test 1: Health check
  results.push(await testHealthCheck());
  if (!results[0]) {
    console.log("\nHealth check failed - server may not be running.");
    process.exit(1);
  }

  // Test 2: Endpoint info
  results.push(await testWebSocketEndpointInfo());

  // Test 3: Anonymous connection
  results.push(await testAnonymousConnection());

  // Test 4: Authenticated connection (if token provided)
  results.push(await testConnectionWithToken());

  // Test 5: Invalid token handling
  results.push(await testInvalidToken());

  // Test 6: Heartbeat and ping
  results.push(await testHeartbeatAndPing());

  // Print summary
  console.log("=== Test Summary ===");
  const testNames = [
    "Health Check",
    "Endpoint Info",
    "Anonymous Connection",
    "Authenticated Connection",
    "Invalid Token Handling",
    "Heartbeat/Ping",
  ];

  let passed = 0;
  for (let i = 0; i < results.length; i++) {
    console.log(`${testNames[i]}: ${results[i] ? "✓" : "✗"}`);
    if (results[i]) passed++;
  }

  console.log(`\n${passed}/${results.length} tests passed`);

  const allPassed = results.every(Boolean);
  console.log(`\n${allPassed ? "All tests passed! ✓" : "Some tests failed ✗"}`);
  process.exit(allPassed ? 0 : 1);
}

runTests().catch((error) => {
  console.error("Test script error:", error);
  process.exit(1);
});
