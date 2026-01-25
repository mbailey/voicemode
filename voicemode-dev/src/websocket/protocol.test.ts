/**
 * Unit tests for WebSocket protocol types and validation
 */

import { describe, it, expect } from "vitest";
import {
  validateClientMessage,
  parseClientMessage,
  isClientMessage,
  createSpeakMessage,
  createListenMessage,
  createStopMessage,
  createAckMessage,
  createErrorMessage,
  createHeartbeatMessage,
  createConnectedMessage,
  createSessionResumedMessage,
  generateMessageId,
  generateSessionToken,
  MessageErrorCode,
  ClientMessage,
  AuthMessage,
  ReadyMessage,
  TranscriptionMessage,
  HeartbeatMessage,
  ResumeMessage,
  SpeakMessage,
  ListenMessage,
  StopMessage,
  AckMessage,
  ServerHeartbeatMessage,
  SessionResumedMessage,
  ConnectedMessage,
} from "./protocol";

describe("Message Validation", () => {
  describe("validateClientMessage", () => {
    it("rejects non-object messages", () => {
      expect(validateClientMessage(null)).toEqual({
        valid: false,
        error: "Message must be an object",
        errorCode: MessageErrorCode.INVALID_MESSAGE,
      });
      expect(validateClientMessage("string")).toEqual({
        valid: false,
        error: "Message must be an object",
        errorCode: MessageErrorCode.INVALID_MESSAGE,
      });
      expect(validateClientMessage(123)).toEqual({
        valid: false,
        error: "Message must be an object",
        errorCode: MessageErrorCode.INVALID_MESSAGE,
      });
    });

    it("rejects messages without type field", () => {
      expect(validateClientMessage({})).toEqual({
        valid: false,
        error: "Message must have a 'type' field",
        errorCode: MessageErrorCode.MISSING_FIELD,
      });
      expect(validateClientMessage({ data: "test" })).toEqual({
        valid: false,
        error: "Message must have a 'type' field",
        errorCode: MessageErrorCode.MISSING_FIELD,
      });
    });

    it("rejects unknown message types", () => {
      const result = validateClientMessage({ type: "unknown_type" });
      expect(result.valid).toBe(false);
      expect(result.errorCode).toBe(MessageErrorCode.UNKNOWN_TYPE);
    });

    it("validates heartbeat messages", () => {
      expect(validateClientMessage({ type: "heartbeat" })).toEqual({
        valid: true,
      });
    });

    it("validates auth messages", () => {
      // Valid auth message
      expect(
        validateClientMessage({
          type: "auth",
          token: "valid.jwt.token123",
        })
      ).toEqual({ valid: true });

      // Missing token
      expect(validateClientMessage({ type: "auth" })).toEqual({
        valid: false,
        error: "Auth message must have a 'token' field (string)",
        errorCode: MessageErrorCode.MISSING_FIELD,
      });

      // Token too short
      expect(
        validateClientMessage({ type: "auth", token: "short" })
      ).toEqual({
        valid: false,
        error: "Token appears to be invalid (too short)",
        errorCode: MessageErrorCode.INVALID_TOKEN,
      });
    });

    it("validates ready messages", () => {
      // Minimal ready message
      expect(validateClientMessage({ type: "ready" })).toEqual({
        valid: true,
      });

      // Ready with device info
      expect(
        validateClientMessage({
          type: "ready",
          device: { platform: "ios", appVersion: "1.0.0" },
        })
      ).toEqual({ valid: true });

      // Ready with capabilities
      expect(
        validateClientMessage({
          type: "ready",
          capabilities: { tts: true, stt: true },
        })
      ).toEqual({ valid: true });

      // Invalid device field
      expect(
        validateClientMessage({ type: "ready", device: "invalid" })
      ).toEqual({
        valid: false,
        error: "'device' field must be an object",
        errorCode: MessageErrorCode.INVALID_TYPE,
      });

      // Invalid capabilities field
      expect(
        validateClientMessage({ type: "ready", capabilities: "invalid" })
      ).toEqual({
        valid: false,
        error: "'capabilities' field must be an object",
        errorCode: MessageErrorCode.INVALID_TYPE,
      });
    });

    it("validates transcription messages", () => {
      // Valid transcription
      expect(
        validateClientMessage({
          type: "transcription",
          text: "Hello world",
          id: "msg-123",
        })
      ).toEqual({ valid: true });

      // Valid with optional fields
      expect(
        validateClientMessage({
          type: "transcription",
          text: "Hello",
          id: "msg-123",
          confidence: 0.95,
          duration: 2.5,
          language: "en",
        })
      ).toEqual({ valid: true });

      // Missing text
      expect(
        validateClientMessage({ type: "transcription", id: "msg-123" })
      ).toEqual({
        valid: false,
        error: "Transcription message must have a 'text' field (string)",
        errorCode: MessageErrorCode.MISSING_FIELD,
      });

      // Missing id
      expect(
        validateClientMessage({ type: "transcription", text: "Hello" })
      ).toEqual({
        valid: false,
        error: "Transcription message must have an 'id' field (string)",
        errorCode: MessageErrorCode.MISSING_FIELD,
      });
    });

    it("validates resume messages", () => {
      // Valid resume message
      expect(
        validateClientMessage({
          type: "resume",
          sessionToken: "sess-1234567890abcdef",
        })
      ).toEqual({ valid: true });

      // Missing sessionToken
      expect(validateClientMessage({ type: "resume" })).toEqual({
        valid: false,
        error: "Resume message must have a 'sessionToken' field (string)",
        errorCode: MessageErrorCode.MISSING_FIELD,
      });

      // Session token too short
      expect(
        validateClientMessage({ type: "resume", sessionToken: "short" })
      ).toEqual({
        valid: false,
        error: "Session token appears to be invalid (too short)",
        errorCode: MessageErrorCode.INVALID_TOKEN,
      });
    });
  });

  describe("parseClientMessage", () => {
    it("parses valid JSON string messages", () => {
      const result = parseClientMessage('{"type":"heartbeat"}');
      expect(result.error).toBeUndefined();
      expect(result.message).toEqual({ type: "heartbeat" });
    });

    it("parses ArrayBuffer messages", () => {
      const encoder = new TextEncoder();
      const encoded = encoder.encode('{"type":"heartbeat"}');
      // Create a proper ArrayBuffer from the Uint8Array
      const buffer = new ArrayBuffer(encoded.byteLength);
      new Uint8Array(buffer).set(encoded);
      const result = parseClientMessage(buffer);
      expect(result.error).toBeUndefined();
      expect(result.message).toEqual({ type: "heartbeat" });
    });

    it("returns error for invalid JSON", () => {
      const result = parseClientMessage("not json");
      expect(result.message).toBeUndefined();
      expect(result.error).toEqual({
        valid: false,
        error: "Invalid JSON",
        errorCode: MessageErrorCode.PARSE_ERROR,
      });
    });

    it("returns error for invalid message structure", () => {
      const result = parseClientMessage('{"data":"test"}');
      expect(result.message).toBeUndefined();
      expect(result.error?.errorCode).toBe(MessageErrorCode.MISSING_FIELD);
    });
  });

  describe("isClientMessage", () => {
    it("returns true for valid messages", () => {
      expect(isClientMessage({ type: "heartbeat" })).toBe(true);
      expect(
        isClientMessage({ type: "auth", token: "valid.token.here123" })
      ).toBe(true);
      expect(isClientMessage({ type: "ready" })).toBe(true);
      expect(
        isClientMessage({
          type: "transcription",
          text: "Hello",
          id: "123",
        })
      ).toBe(true);
    });

    it("returns false for invalid messages", () => {
      expect(isClientMessage(null)).toBe(false);
      expect(isClientMessage({})).toBe(false);
      expect(isClientMessage({ type: "unknown" })).toBe(false);
      expect(isClientMessage({ type: "auth" })).toBe(false);
    });
  });
});

describe("Message Factories", () => {
  describe("generateMessageId", () => {
    it("generates unique IDs", () => {
      const id1 = generateMessageId();
      const id2 = generateMessageId();
      expect(id1).not.toBe(id2);
    });

    it("generates IDs with expected format", () => {
      const id = generateMessageId();
      expect(id).toMatch(/^msg-\d+-[a-z0-9]+$/);
    });
  });

  describe("createSpeakMessage", () => {
    it("creates a speak message with required fields", () => {
      const msg = createSpeakMessage("Hello world");
      expect(msg.type).toBe("speak");
      expect(msg.text).toBe("Hello world");
      expect(msg.id).toBeDefined();
      expect(msg.timestamp).toBeDefined();
    });

    it("creates a speak message with optional fields", () => {
      const msg = createSpeakMessage("Hello", {
        voice: "alloy",
        speed: 1.5,
        waitForResponse: true,
        instructions: "Speak clearly",
      });
      expect(msg.voice).toBe("alloy");
      expect(msg.speed).toBe(1.5);
      expect(msg.waitForResponse).toBe(true);
      expect(msg.instructions).toBe("Speak clearly");
    });
  });

  describe("createListenMessage", () => {
    it("creates a listen message with defaults", () => {
      const msg = createListenMessage();
      expect(msg.type).toBe("listen");
      expect(msg.id).toBeDefined();
      expect(msg.timestamp).toBeDefined();
    });

    it("creates a listen message with options", () => {
      const msg = createListenMessage({
        maxDuration: 60,
        minDuration: 1,
        useVAD: true,
        language: "en",
        prompt: "Listen for a name",
      });
      expect(msg.maxDuration).toBe(60);
      expect(msg.minDuration).toBe(1);
      expect(msg.useVAD).toBe(true);
      expect(msg.language).toBe("en");
      expect(msg.prompt).toBe("Listen for a name");
    });
  });

  describe("createStopMessage", () => {
    it("creates a stop message with defaults", () => {
      const msg = createStopMessage();
      expect(msg.type).toBe("stop");
      expect(msg.target).toBeUndefined();
      expect(msg.reason).toBeUndefined();
    });

    it("creates a stop message with target and reason", () => {
      const msg = createStopMessage("tts", "User interrupted");
      expect(msg.target).toBe("tts");
      expect(msg.reason).toBe("User interrupted");
    });
  });

  describe("createAckMessage", () => {
    it("creates an OK ack message", () => {
      const msg = createAckMessage("msg-123", "ok");
      expect(msg.type).toBe("ack");
      expect(msg.id).toBe("msg-123");
      expect(msg.status).toBe("ok");
      expect(msg.error).toBeUndefined();
    });

    it("creates an error ack message", () => {
      const msg = createAckMessage(
        "msg-123",
        "error",
        "Something went wrong",
        "INTERNAL_ERROR"
      );
      expect(msg.status).toBe("error");
      expect(msg.error).toBe("Something went wrong");
      expect(msg.errorCode).toBe("INTERNAL_ERROR");
    });
  });

  describe("createErrorMessage", () => {
    it("creates an error message", () => {
      const msg = createErrorMessage(
        "AUTH_FAILED",
        "Authentication failed",
        { reason: "Token expired" }
      );
      expect(msg.type).toBe("error");
      expect(msg.code).toBe("AUTH_FAILED");
      expect(msg.message).toBe("Authentication failed");
      expect(msg.details).toEqual({ reason: "Token expired" });
      expect(msg.timestamp).toBeDefined();
    });
  });

  describe("createHeartbeatMessage", () => {
    it("creates a server heartbeat message", () => {
      const msg = createHeartbeatMessage();
      expect(msg.type).toBe("heartbeat");
      expect(msg.timestamp).toBeDefined();
      expect(typeof msg.timestamp).toBe("number");
    });

    it("generates current timestamp", () => {
      const before = Date.now();
      const msg = createHeartbeatMessage();
      const after = Date.now();
      expect(msg.timestamp).toBeGreaterThanOrEqual(before);
      expect(msg.timestamp).toBeLessThanOrEqual(after);
    });
  });

  describe("generateSessionToken", () => {
    it("generates unique session tokens", () => {
      const token1 = generateSessionToken();
      const token2 = generateSessionToken();
      expect(token1).not.toBe(token2);
    });

    it("generates tokens with expected format", () => {
      const token = generateSessionToken();
      expect(token).toMatch(/^sess-[a-f0-9]{48}$/);
    });

    it("generates tokens with sufficient length for security", () => {
      const token = generateSessionToken();
      // sess- prefix (5) + 48 hex chars = 53 total chars
      expect(token.length).toBe(53);
    });
  });

  describe("createSessionResumedMessage", () => {
    it("creates a session_resumed message with all fields", () => {
      const msg = createSessionResumedMessage(
        "sess-abc123",
        5,
        true,
        30000,
        "user-123"
      );
      expect(msg.type).toBe("session_resumed");
      expect(msg.sessionToken).toBe("sess-abc123");
      expect(msg.queuedMessageCount).toBe(5);
      expect(msg.authenticated).toBe(true);
      expect(msg.disconnectedDuration).toBe(30000);
      expect(msg.userId).toBe("user-123");
      expect(msg.timestamp).toBeDefined();
    });

    it("creates a session_resumed message for unauthenticated session", () => {
      const msg = createSessionResumedMessage(
        "sess-xyz789",
        0,
        false,
        0,
        null
      );
      expect(msg.authenticated).toBe(false);
      expect(msg.userId).toBeNull();
      expect(msg.queuedMessageCount).toBe(0);
    });
  });

  describe("createConnectedMessage", () => {
    it("creates a connected message for authenticated user", () => {
      const msg = createConnectedMessage(true, "sess-abc123", "user-123");
      expect(msg.type).toBe("connected");
      expect(msg.authenticated).toBe(true);
      expect(msg.sessionId).toBe("sess-abc123");
      expect(msg.userId).toBe("user-123");
      expect(msg.timestamp).toBeDefined();
    });

    it("creates a connected message for anonymous user", () => {
      const msg = createConnectedMessage(false, "sess-xyz789", null);
      expect(msg.authenticated).toBe(false);
      expect(msg.userId).toBeNull();
      expect(msg.sessionId).toBe("sess-xyz789");
    });
  });
});

describe("Type Definitions", () => {
  // These tests verify that the types are correctly defined
  // They mainly serve as compile-time checks

  it("AuthMessage has correct structure", () => {
    const msg: AuthMessage = {
      type: "auth",
      token: "jwt-token",
      id: "msg-1",
    };
    expect(msg.type).toBe("auth");
  });

  it("ReadyMessage has correct structure", () => {
    const msg: ReadyMessage = {
      type: "ready",
      device: {
        platform: "ios",
        appVersion: "1.0.0",
        model: "iPhone 15",
        osVersion: "17.0",
      },
      capabilities: {
        tts: true,
        stt: true,
        maxAudioDuration: 60,
      },
    };
    expect(msg.type).toBe("ready");
  });

  it("TranscriptionMessage has correct structure", () => {
    const msg: TranscriptionMessage = {
      type: "transcription",
      text: "Hello world",
      id: "msg-123",
      confidence: 0.95,
      duration: 2.5,
      isFinal: true,
      language: "en",
    };
    expect(msg.type).toBe("transcription");
  });

  it("HeartbeatMessage has correct structure", () => {
    const msg: HeartbeatMessage = {
      type: "heartbeat",
    };
    expect(msg.type).toBe("heartbeat");
  });

  it("SpeakMessage has correct structure", () => {
    const msg: SpeakMessage = {
      type: "speak",
      id: "msg-1",
      text: "Hello",
      voice: "alloy",
      speed: 1.0,
      waitForResponse: true,
      instructions: "Speak clearly",
    };
    expect(msg.type).toBe("speak");
  });

  it("ListenMessage has correct structure", () => {
    const msg: ListenMessage = {
      type: "listen",
      id: "msg-1",
      maxDuration: 60,
      minDuration: 1,
      useVAD: true,
      language: "en",
      prompt: "Listen for a name",
    };
    expect(msg.type).toBe("listen");
  });

  it("StopMessage has correct structure", () => {
    const msg: StopMessage = {
      type: "stop",
      target: "all",
      reason: "User cancelled",
    };
    expect(msg.type).toBe("stop");
  });

  it("AckMessage has correct structure", () => {
    const msg: AckMessage = {
      type: "ack",
      id: "msg-1",
      status: "ok",
      timestamp: Date.now(),
    };
    expect(msg.type).toBe("ack");
  });

  it("ServerHeartbeatMessage has correct structure", () => {
    const msg: ServerHeartbeatMessage = {
      type: "heartbeat",
      timestamp: Date.now(),
    };
    expect(msg.type).toBe("heartbeat");
    expect(typeof msg.timestamp).toBe("number");
  });

  it("ResumeMessage has correct structure", () => {
    const msg: ResumeMessage = {
      type: "resume",
      sessionToken: "sess-abc123def456",
      id: "msg-1",
    };
    expect(msg.type).toBe("resume");
    expect(msg.sessionToken).toBe("sess-abc123def456");
  });

  it("SessionResumedMessage has correct structure", () => {
    const msg: SessionResumedMessage = {
      type: "session_resumed",
      sessionToken: "sess-abc123",
      queuedMessageCount: 3,
      authenticated: true,
      userId: "user-123",
      disconnectedDuration: 5000,
      timestamp: Date.now(),
    };
    expect(msg.type).toBe("session_resumed");
    expect(msg.queuedMessageCount).toBe(3);
    expect(msg.disconnectedDuration).toBe(5000);
  });

  it("ConnectedMessage has correct structure with session ID", () => {
    const msg: ConnectedMessage = {
      type: "connected",
      authenticated: true,
      userId: "user-123",
      sessionId: "sess-abc123",
      timestamp: Date.now(),
    };
    expect(msg.type).toBe("connected");
    expect(msg.sessionId).toBe("sess-abc123");
  });
});
