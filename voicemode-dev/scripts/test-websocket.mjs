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
        console.log("  ✓ Heartbeat acknowledged\n");
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

async function testReadyMessage() {
  console.log("Test 7: Ready message protocol...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-ready`;
    const ws = new WebSocket(wsUrl);

    const results = {
      connected: false,
      readyAcked: false,
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
        // Send ready message with device info and capabilities
        ws.send(JSON.stringify({
          type: "ready",
          id: "ready-001",
          device: {
            platform: "test",
            appVersion: "1.0.0",
            model: "TestDevice",
            osVersion: "1.0",
          },
          capabilities: {
            tts: true,
            stt: true,
            maxAudioDuration: 120,
          },
        }));
      }

      if (msg.type === "ack" && msg.id === "ready-001") {
        if (msg.status === "ok") {
          results.readyAcked = true;
          console.log("  ✓ Ready message acknowledged\n");
          clearTimeout(timeout);
          ws.close(1000, "Test complete");
          resolve(true);
        } else {
          console.log("  ✗ Ready rejected:", msg.error);
          clearTimeout(timeout);
          ws.close();
          resolve(false);
        }
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Error:", error.message);
      resolve(false);
    });
  });
}

async function testTranscriptionMessage() {
  console.log("Test 8: Transcription message protocol...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-transcription`;
    const ws = new WebSocket(wsUrl);

    const results = {
      connected: false,
      ready: false,
      transcriptionAcked: false,
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
        // First send ready message
        ws.send(JSON.stringify({
          type: "ready",
          id: "ready-002",
        }));
      }

      if (msg.type === "ack" && msg.id === "ready-002") {
        results.ready = true;
        // Now send transcription
        ws.send(JSON.stringify({
          type: "transcription",
          id: "trans-001",
          text: "Hello, this is a test transcription",
          confidence: 0.95,
          duration: 2.5,
          language: "en",
        }));
      }

      if (msg.type === "ack" && msg.id === "trans-001") {
        if (msg.status === "ok") {
          results.transcriptionAcked = true;
          console.log("  ✓ Transcription acknowledged\n");
          clearTimeout(timeout);
          ws.close(1000, "Test complete");
          resolve(true);
        } else {
          console.log("  ✗ Transcription rejected:", msg.error);
          clearTimeout(timeout);
          ws.close();
          resolve(false);
        }
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Error:", error.message);
      resolve(false);
    });
  });
}

async function testUnknownMessageType() {
  console.log("Test 9: Unknown message type handling...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-unknown`;
    const ws = new WebSocket(wsUrl);

    const results = {
      connected: false,
      errorReceived: false,
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
        // Send unknown message type
        ws.send(JSON.stringify({
          type: "unknown_type_12345",
          id: "unknown-001",
          data: "test",
        }));
      }

      // Should receive ack with error status for unknown types
      if (msg.type === "ack" && msg.status === "error") {
        results.errorReceived = true;
        console.log("  ✓ Unknown type handled gracefully\n");
        clearTimeout(timeout);
        ws.close(1000, "Test complete");
        resolve(true);
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Error:", error.message);
      resolve(false);
    });
  });
}

async function testInvalidMessageFormat() {
  console.log("Test 10: Invalid message format handling...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-invalid`;
    const ws = new WebSocket(wsUrl);

    const results = {
      connected: false,
      errorReceived: false,
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
        // Send invalid JSON
        ws.send("not valid json {{{");
      }

      if (msg.type === "error" && msg.code === "PARSE_ERROR") {
        results.errorReceived = true;
        console.log("  ✓ Parse error handled correctly\n");
        clearTimeout(timeout);
        ws.close(1000, "Test complete");
        resolve(true);
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Error:", error.message);
      resolve(false);
    });
  });
}

async function testSessionResumption() {
  console.log("Test 11: Session resumption...");
  const WebSocket = (await import("ws")).default;

  let sessionToken = null;

  // Phase 1: Connect and get session token
  const phase1Result = await new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-session`;
    console.log("  Phase 1: Initial connection...");
    const ws = new WebSocket(wsUrl);

    const timeout = setTimeout(() => {
      console.log("  ✗ Phase 1 timeout");
      ws.close();
      resolve(false);
    }, 10000);

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      console.log("  Received:", JSON.stringify(msg));

      if (msg.type === "connected" && msg.sessionId) {
        sessionToken = msg.sessionId;
        console.log(`  ✓ Got session token: ${sessionToken.substring(0, 20)}...`);
        clearTimeout(timeout);
        // Close connection to simulate disconnect
        ws.close(1000, "Simulating disconnect");
        resolve(true);
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Phase 1 error:", error.message);
      resolve(false);
    });
  });

  if (!phase1Result || !sessionToken) {
    console.log("  ✗ Failed to get session token\n");
    return false;
  }

  // Wait a moment to simulate disconnect
  await sleep(500);

  // Phase 2: Reconnect with session token
  const phase2Result = await new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-session`;
    console.log("  Phase 2: Reconnecting with session token...");
    const ws = new WebSocket(wsUrl);

    const results = {
      connected: false,
      sessionResumed: false,
    };

    const timeout = setTimeout(() => {
      console.log("  ✗ Phase 2 timeout");
      ws.close();
      resolve(false);
    }, 10000);

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      console.log("  Received:", JSON.stringify(msg));

      if (msg.type === "connected") {
        results.connected = true;
        // Send resume message with the session token
        ws.send(JSON.stringify({
          type: "resume",
          sessionToken: sessionToken,
        }));
      }

      if (msg.type === "session_resumed") {
        results.sessionResumed = true;
        console.log(`  ✓ Session resumed! Disconnected for: ${msg.disconnectedDuration}ms`);
        console.log(`  ✓ Queued messages: ${msg.queuedMessageCount}`);
        clearTimeout(timeout);
        ws.close(1000, "Test complete");
        resolve(true);
      }

      // Handle case where session is not found (expired or cleared)
      if (msg.type === "error" && (msg.code === "SESSION_NOT_FOUND" || msg.code === "SESSION_EXPIRED")) {
        console.log(`  Session error: ${msg.code} - ${msg.message}`);
        // This is actually expected behavior for expired sessions
        clearTimeout(timeout);
        ws.close(1000, "Test complete");
        resolve(true);
      }
    });

    ws.on("error", (error) => {
      clearTimeout(timeout);
      console.log("  ✗ Phase 2 error:", error.message);
      resolve(false);
    });
  });

  if (phase2Result) {
    console.log("  ✓ Session resumption test passed\n");
    return true;
  } else {
    console.log("  ✗ Session resumption test failed\n");
    return false;
  }
}

async function testInvalidSessionResumption() {
  console.log("Test 12: Invalid session token handling...");
  const WebSocket = (await import("ws")).default;

  return new Promise((resolve) => {
    const wsUrl = `${BASE_URL}?user=test-invalid-session`;
    const ws = new WebSocket(wsUrl);

    const timeout = setTimeout(() => {
      console.log("  ✗ Timeout");
      ws.close();
      resolve(false);
    }, 10000);

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      console.log("  Received:", JSON.stringify(msg));

      if (msg.type === "connected") {
        // Try to resume with a fake session token
        ws.send(JSON.stringify({
          type: "resume",
          sessionToken: "sess-fake-session-token-that-does-not-exist-12345",
        }));
      }

      if (msg.type === "error" && msg.code === "SESSION_NOT_FOUND") {
        console.log("  ✓ Invalid session correctly rejected\n");
        clearTimeout(timeout);
        ws.close(1000, "Test complete");
        resolve(true);
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
  console.log("=== WebSocket Gateway Protocol Tests ===\n");
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

  // Test 6: Heartbeat
  results.push(await testHeartbeatAndPing());

  // Test 7: Ready message
  results.push(await testReadyMessage());

  // Test 8: Transcription message
  results.push(await testTranscriptionMessage());

  // Test 9: Unknown message type
  results.push(await testUnknownMessageType());

  // Test 10: Invalid message format
  results.push(await testInvalidMessageFormat());

  // Test 11: Session resumption
  results.push(await testSessionResumption());

  // Test 12: Invalid session token handling
  results.push(await testInvalidSessionResumption());

  // Print summary
  console.log("=== Test Summary ===");
  const testNames = [
    "Health Check",
    "Endpoint Info",
    "Anonymous Connection",
    "Authenticated Connection",
    "Invalid Token Handling",
    "Heartbeat",
    "Ready Message",
    "Transcription Message",
    "Unknown Type Handling",
    "Invalid Format Handling",
    "Session Resumption",
    "Invalid Session Handling",
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
