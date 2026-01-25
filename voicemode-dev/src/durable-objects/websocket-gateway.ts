/**
 * WebSocketGateway Durable Object
 *
 * Manages WebSocket connections for a single user session.
 * Each user gets their own Durable Object instance (keyed by user ID).
 *
 * Responsibilities:
 * - Accept and manage WebSocket connections from mobile apps
 * - Maintain connection state (authenticated, ready, etc.)
 * - Handle message routing between Claude.ai (via MCP) and mobile apps
 * - Track heartbeats and connection health
 */

import { DurableObject } from "cloudflare:workers";
import {
  ClientMessage,
  AuthMessage,
  ReadyMessage,
  TranscriptionMessage,
  HeartbeatMessage,
  parseClientMessage,
  createAckMessage,
  createSpeakMessage,
  createListenMessage,
  createStopMessage,
  createHeartbeatMessage,
  MessageErrorCode,
} from "../websocket/protocol";

export interface Env {
  WEBSOCKET_GATEWAY: DurableObjectNamespace;
  ENVIRONMENT: string;
}

// ============================================================================
// Heartbeat and Keepalive Configuration
// ============================================================================

/** Interval between server heartbeat pings (in milliseconds) */
const HEARTBEAT_INTERVAL_MS = 30_000; // 30 seconds

/** Timeout for considering a connection stale (in milliseconds) */
const STALE_CONNECTION_TIMEOUT_MS = 90_000; // 90 seconds (3 missed heartbeats)

/** WebSocket close codes */
const CLOSE_CODE_NORMAL = 1000;
const CLOSE_CODE_GOING_AWAY = 1001;
const CLOSE_CODE_POLICY_VIOLATION = 1008;

/** Authenticated user info from JWT validation */
interface AuthenticatedUser {
  userId: string;
  email?: string;
  name?: string;
  picture?: string;
}

/** Connection state for a WebSocket client */
interface ConnectionState {
  /** WebSocket connection */
  websocket: WebSocket;
  /** User ID from JWT token */
  userId: string | null;
  /** Whether the connection is authenticated */
  authenticated: boolean;
  /** Full user info from JWT (if authenticated) */
  userInfo?: AuthenticatedUser;
  /** Whether the client has sent the ready message */
  ready: boolean;
  /** Last activity timestamp (for keepalive) */
  lastActivity: number;
  /** Connection established timestamp */
  connectedAt: number;
  /** Device info from client */
  deviceInfo?: {
    platform?: string;
    appVersion?: string;
  };
  /** Client capabilities (TTS, STT support) */
  capabilities?: {
    tts?: boolean;
    stt?: boolean;
    maxAudioDuration?: number;
  };
  /** Last transcription received from client */
  lastTranscription?: {
    id: string;
    text: string;
    confidence?: number;
    duration?: number;
    language?: string;
    receivedAt: number;
  };
}

export class WebSocketGateway extends DurableObject {
  /** Active connections (a user may have multiple devices) */
  private connections: Map<WebSocket, ConnectionState> = new Map();

  /** Whether heartbeat alarm is currently scheduled */
  private heartbeatAlarmScheduled = false;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
  }

  // ============================================================================
  // Heartbeat and Keepalive Management
  // ============================================================================

  /**
   * Durable Object alarm handler.
   * Called periodically to send heartbeats and check for stale connections.
   */
  async alarm(): Promise<void> {
    this.heartbeatAlarmScheduled = false;

    if (this.connections.size === 0) {
      console.log("[WebSocketGateway] No connections, skipping heartbeat");
      return;
    }

    const now = Date.now();
    const staleConnections: WebSocket[] = [];

    console.log(
      `[WebSocketGateway] Heartbeat check. Connections: ${this.connections.size}`
    );

    // Check each connection and send heartbeat
    for (const [ws, state] of this.connections) {
      const timeSinceActivity = now - state.lastActivity;

      // Check if connection is stale
      if (timeSinceActivity > STALE_CONNECTION_TIMEOUT_MS) {
        console.log(
          `[WebSocketGateway] Stale connection detected. User: ${state.userId}, ` +
            `Last activity: ${Math.round(timeSinceActivity / 1000)}s ago`
        );
        staleConnections.push(ws);
        continue;
      }

      // Send heartbeat to active connections
      try {
        this.send(ws, createHeartbeatMessage());
        console.log(
          `[WebSocketGateway] Heartbeat sent. User: ${state.userId}, ` +
            `Last activity: ${Math.round(timeSinceActivity / 1000)}s ago`
        );
      } catch (e) {
        console.error(
          `[WebSocketGateway] Failed to send heartbeat. User: ${state.userId}`,
          e
        );
        staleConnections.push(ws);
      }
    }

    // Close stale connections
    for (const ws of staleConnections) {
      this.closeStaleConnection(ws);
    }

    // Schedule next heartbeat if we still have connections
    if (this.connections.size > 0) {
      this.scheduleHeartbeatAlarm();
    }
  }

  /**
   * Schedule the next heartbeat alarm.
   */
  private scheduleHeartbeatAlarm(): void {
    if (this.heartbeatAlarmScheduled) {
      return;
    }

    const nextAlarmTime = Date.now() + HEARTBEAT_INTERVAL_MS;
    this.ctx.storage.setAlarm(nextAlarmTime);
    this.heartbeatAlarmScheduled = true;

    console.log(
      `[WebSocketGateway] Heartbeat alarm scheduled for ${new Date(nextAlarmTime).toISOString()}`
    );
  }

  /**
   * Close a stale connection with appropriate logging.
   */
  private closeStaleConnection(ws: WebSocket): void {
    const state = this.connections.get(ws);
    if (!state) {
      return;
    }

    const timeSinceActivity = Date.now() - state.lastActivity;
    const timeSinceConnect = Date.now() - state.connectedAt;

    console.log(
      `[WebSocketGateway] Closing stale connection. ` +
        `User: ${state.userId}, ` +
        `Connected for: ${Math.round(timeSinceConnect / 1000)}s, ` +
        `Inactive for: ${Math.round(timeSinceActivity / 1000)}s`
    );

    // Send error message before closing
    try {
      this.send(ws, {
        type: "error",
        code: "CONNECTION_TIMEOUT",
        message: "Connection closed due to inactivity",
        timestamp: Date.now(),
      });
    } catch (e) {
      // Ignore send errors for stale connections
    }

    // Close the WebSocket
    try {
      ws.close(CLOSE_CODE_POLICY_VIOLATION, "Connection timeout");
    } catch (e) {
      console.error("[WebSocketGateway] Error closing stale WebSocket:", e);
    }

    // Remove from connections map
    this.connections.delete(ws);

    console.log(
      `[WebSocketGateway] Stale connection removed. Remaining: ${this.connections.size}`
    );
  }

  /**
   * Handle incoming HTTP requests to the Durable Object.
   * This is the entry point for WebSocket upgrade requests.
   */
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    // Health check endpoint
    if (url.pathname === "/health") {
      return new Response(
        JSON.stringify({
          status: "ok",
          connections: this.connections.size,
          timestamp: Date.now(),
        }),
        {
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // WebSocket upgrade request
    if (request.headers.get("Upgrade") === "websocket") {
      return this.handleWebSocketUpgrade(request);
    }

    // Connection info endpoint (for debugging)
    if (url.pathname === "/info") {
      const info = this.getConnectionInfo();
      return new Response(JSON.stringify(info, null, 2), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response("Expected WebSocket upgrade", { status: 426 });
  }

  /**
   * Handle WebSocket upgrade request.
   * Creates a new WebSocket pair and accepts the connection.
   * Extracts authenticated user info from request headers if present.
   */
  private async handleWebSocketUpgrade(request: Request): Promise<Response> {
    // Create WebSocket pair (client and server sides)
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // Accept the WebSocket connection on the server side
    this.ctx.acceptWebSocket(server);

    // Check for authenticated user info from the worker
    let authenticatedUser: AuthenticatedUser | undefined;
    const userHeader = request.headers.get("X-Authenticated-User");
    if (userHeader) {
      try {
        authenticatedUser = JSON.parse(userHeader);
        console.log(
          `[WebSocketGateway] Authenticated user: ${authenticatedUser?.userId}`
        );
      } catch (e) {
        console.error("[WebSocketGateway] Failed to parse user info header:", e);
      }
    }

    // Initialize connection state
    const state: ConnectionState = {
      websocket: server,
      userId: authenticatedUser?.userId || null,
      authenticated: !!authenticatedUser,
      userInfo: authenticatedUser,
      ready: false,
      lastActivity: Date.now(),
      connectedAt: Date.now(),
    };
    this.connections.set(server, state);

    console.log(
      `[WebSocketGateway] Connection state change: CONNECTED. ` +
        `User: ${state.userId || 'anonymous'}, Authenticated: ${state.authenticated}, Total: ${this.connections.size}`
    );

    // Send welcome message with authentication status
    this.send(server, {
      type: "connected",
      authenticated: state.authenticated,
      userId: state.userId,
      timestamp: Date.now(),
    });

    // Schedule heartbeat alarm if this is the first connection
    this.scheduleHeartbeatAlarm();

    // Return the client side of the WebSocket pair
    return new Response(null, {
      status: 101,
      webSocket: client,
    });
  }

  /**
   * Handle incoming WebSocket messages.
   * Called by the Durable Object runtime for each message.
   */
  async webSocketMessage(
    ws: WebSocket,
    message: string | ArrayBuffer
  ): Promise<void> {
    const state = this.connections.get(ws);
    if (!state) {
      console.error("[WebSocketGateway] Message from unknown connection");
      return;
    }

    // Update last activity timestamp
    state.lastActivity = Date.now();

    // Parse and validate message using protocol
    const result = parseClientMessage(message);
    if (result.error) {
      // Handle parse/validation errors
      const errorCode = result.error.errorCode || MessageErrorCode.INVALID_MESSAGE;

      // For unknown message types, log but don't send error (graceful handling)
      if (errorCode === MessageErrorCode.UNKNOWN_TYPE) {
        console.log(`[WebSocketGateway] ${result.error.error}`);
        // Send ack with error status for unknown types
        this.send(ws, createAckMessage(
          "unknown",
          "error",
          result.error.error,
          errorCode
        ));
        return;
      }

      this.sendError(ws, errorCode, result.error.error || "Invalid message");
      return;
    }

    // Handle validated message
    await this.handleMessage(ws, state, result.message);
  }

  /**
   * Handle WebSocket close event.
   */
  async webSocketClose(
    ws: WebSocket,
    code: number,
    reason: string,
    wasClean: boolean
  ): Promise<void> {
    const state = this.connections.get(ws);
    if (state) {
      const sessionDuration = Date.now() - state.connectedAt;
      const timeSinceActivity = Date.now() - state.lastActivity;

      console.log(
        `[WebSocketGateway] Connection state change: CLOSED. ` +
          `User: ${state.userId || 'anonymous'}, ` +
          `Code: ${code}, Reason: ${reason || 'none'}, ` +
          `Clean: ${wasClean}, ` +
          `Session: ${Math.round(sessionDuration / 1000)}s, ` +
          `Last activity: ${Math.round(timeSinceActivity / 1000)}s ago`
      );
      this.connections.delete(ws);
    }
    console.log(
      `[WebSocketGateway] Connections remaining: ${this.connections.size}`
    );
  }

  /**
   * Handle WebSocket error event.
   */
  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    const state = this.connections.get(ws);
    const sessionDuration = state ? Date.now() - state.connectedAt : 0;

    console.error(
      `[WebSocketGateway] Connection state change: ERROR. ` +
        `User: ${state?.userId || 'unknown'}, ` +
        `Session: ${Math.round(sessionDuration / 1000)}s`,
      error
    );
    this.connections.delete(ws);
  }

  /**
   * Handle a typed message from a client.
   * Dispatches to specific handlers based on message type.
   */
  private async handleMessage(
    ws: WebSocket,
    state: ConnectionState,
    msg: ClientMessage
  ): Promise<void> {
    console.log(
      `[WebSocketGateway] Message type: ${msg.type}, authenticated: ${state.authenticated}`
    );

    switch (msg.type) {
      case "auth":
        await this.handleAuthMessage(ws, state, msg);
        break;

      case "ready":
        await this.handleReadyMessage(ws, state, msg);
        break;

      case "transcription":
        await this.handleTranscriptionMessage(ws, state, msg);
        break;

      case "heartbeat":
        this.handleHeartbeatMessage(ws, state, msg);
        break;

      default: {
        // This shouldn't happen due to validation, but handle gracefully
        const unknownMsg = msg as { type: string; id?: string };
        console.log(`[WebSocketGateway] Unexpected message type: ${unknownMsg.type}`);
        this.send(ws, createAckMessage(
          unknownMsg.id || "unknown",
          "error",
          "Unexpected message type",
          MessageErrorCode.UNKNOWN_TYPE
        ));
      }
    }
  }

  /**
   * Handle auth message from client.
   * Used for in-connection authentication (token refresh, late auth).
   */
  private async handleAuthMessage(
    ws: WebSocket,
    state: ConnectionState,
    msg: AuthMessage
  ): Promise<void> {
    console.log(`[WebSocketGateway] Auth message received`);

    // TODO: Validate the token against Auth0
    // For now, acknowledge receipt but note that validation should happen
    // This would require access to the Auth0 validation logic

    // In the current architecture, authentication happens at connection time
    // via query param. This message type is for re-authentication or late auth.
    // Full implementation would validate the token here.

    this.send(ws, createAckMessage(
      msg.id || "auth",
      "ok"
    ));

    // Note: Full token validation would update state.authenticated and state.userInfo
    console.log(`[WebSocketGateway] Auth message acknowledged. Token validation pending implementation.`);
  }

  /**
   * Handle ready message from client.
   * Marks the client as ready to receive commands.
   */
  private async handleReadyMessage(
    ws: WebSocket,
    state: ConnectionState,
    msg: ReadyMessage
  ): Promise<void> {
    console.log(`[WebSocketGateway] Client ready`);

    // Update connection state
    state.ready = true;

    // Store device info if provided
    if (msg.device) {
      state.deviceInfo = {
        platform: msg.device.platform,
        appVersion: msg.device.appVersion,
      };
      console.log(
        `[WebSocketGateway] Device: ${msg.device.platform} v${msg.device.appVersion}`
      );
    }

    // Store capabilities if provided
    if (msg.capabilities) {
      state.capabilities = msg.capabilities;
      console.log(
        `[WebSocketGateway] Capabilities: TTS=${msg.capabilities.tts}, STT=${msg.capabilities.stt}`
      );
    }

    // Acknowledge ready state
    this.send(ws, createAckMessage(msg.id || "ready", "ok"));

    console.log(
      `[WebSocketGateway] Client is now ready. User: ${state.userId}, Device: ${state.deviceInfo?.platform || 'unknown'}`
    );
  }

  /**
   * Handle transcription message from client.
   * Receives STT result in response to a 'listen' command.
   */
  private async handleTranscriptionMessage(
    ws: WebSocket,
    state: ConnectionState,
    msg: TranscriptionMessage
  ): Promise<void> {
    console.log(
      `[WebSocketGateway] Transcription received: "${msg.text.substring(0, 50)}..." (id: ${msg.id})`
    );

    // Validate that client is ready
    if (!state.ready) {
      console.warn(`[WebSocketGateway] Transcription from non-ready client`);
      this.send(ws, createAckMessage(
        msg.id,
        "error",
        "Client must send 'ready' message before transcriptions",
        MessageErrorCode.INVALID_MESSAGE
      ));
      return;
    }

    // Store the transcription for retrieval by MCP server
    // TODO: Implement transcription queue/storage for MCP integration
    state.lastTranscription = {
      id: msg.id,
      text: msg.text,
      confidence: msg.confidence,
      duration: msg.duration,
      language: msg.language,
      receivedAt: Date.now(),
    };

    // Acknowledge receipt
    this.send(ws, createAckMessage(msg.id, "ok"));

    console.log(
      `[WebSocketGateway] Transcription stored. Confidence: ${msg.confidence || 'N/A'}, Duration: ${msg.duration || 'N/A'}s`
    );
  }

  /**
   * Handle heartbeat message from client.
   * Updates activity timestamp and responds immediately to keep connection alive.
   */
  private handleHeartbeatMessage(
    ws: WebSocket,
    state: ConnectionState,
    msg: HeartbeatMessage
  ): void {
    // Note: lastActivity is already updated in webSocketMessage handler
    // Log heartbeat receipt for debugging
    console.log(
      `[WebSocketGateway] Heartbeat received from client. User: ${state.userId || 'anonymous'}`
    );

    // Respond to heartbeat immediately
    this.send(ws, { type: "heartbeat_ack", timestamp: Date.now() });
  }

  // ============================================================================
  // Server → Client Message Senders
  // ============================================================================

  /**
   * Send a speak command to the client.
   * Client should synthesize and play the text via TTS.
   * Returns the message ID for correlation with transcription response.
   */
  sendSpeak(
    ws: WebSocket,
    text: string,
    options?: {
      voice?: string;
      speed?: number;
      waitForResponse?: boolean;
      instructions?: string;
    }
  ): string {
    const msg = createSpeakMessage(text, options);
    this.send(ws, msg);
    console.log(`[WebSocketGateway] Sent speak command (id: ${msg.id}): "${text.substring(0, 50)}..."`);
    return msg.id;
  }

  /**
   * Send a listen command to the client.
   * Client should start recording and send transcription when done.
   * Returns the message ID for correlation with transcription response.
   */
  sendListen(
    ws: WebSocket,
    options?: {
      maxDuration?: number;
      minDuration?: number;
      useVAD?: boolean;
      language?: string;
      prompt?: string;
    }
  ): string {
    const msg = createListenMessage(options);
    this.send(ws, msg);
    console.log(`[WebSocketGateway] Sent listen command (id: ${msg.id})`);
    return msg.id;
  }

  /**
   * Send a stop command to the client.
   * Client should stop the specified operation.
   */
  sendStop(
    ws: WebSocket,
    target?: "tts" | "stt" | "all",
    reason?: string
  ): void {
    const msg = createStopMessage(target, reason);
    this.send(ws, msg);
    console.log(`[WebSocketGateway] Sent stop command (target: ${target || 'all'})`);
  }

  /**
   * Send a speak+listen flow: speak text, then wait for response.
   * Returns the message ID for correlation.
   */
  sendSpeakAndListen(
    ws: WebSocket,
    text: string,
    options?: {
      voice?: string;
      speed?: number;
      listenMaxDuration?: number;
      listenMinDuration?: number;
      useVAD?: boolean;
      language?: string;
    }
  ): string {
    const msg = createSpeakMessage(text, {
      voice: options?.voice,
      speed: options?.speed,
      waitForResponse: true,
    });
    this.send(ws, msg);
    console.log(`[WebSocketGateway] Sent speak+listen command (id: ${msg.id})`);
    return msg.id;
  }

  /**
   * Send a message to a WebSocket client.
   */
  private send(ws: WebSocket, data: unknown): void {
    try {
      ws.send(JSON.stringify(data));
    } catch (e) {
      console.error("[WebSocketGateway] Failed to send message:", e);
    }
  }

  /**
   * Send an error message to a WebSocket client.
   */
  private sendError(ws: WebSocket, code: string, message: string): void {
    this.send(ws, {
      type: "error",
      code,
      message,
      timestamp: Date.now(),
    });
  }

  /**
   * Get information about current connections (for debugging).
   */
  private getConnectionInfo(): object {
    const connections: object[] = [];
    for (const [_, state] of this.connections) {
      connections.push({
        userId: state.userId,
        authenticated: state.authenticated,
        userInfo: state.userInfo ? {
          email: state.userInfo.email,
          name: state.userInfo.name,
        } : undefined,
        ready: state.ready,
        connectedAt: state.connectedAt,
        lastActivity: state.lastActivity,
        deviceInfo: state.deviceInfo,
        capabilities: state.capabilities,
        hasTranscription: !!state.lastTranscription,
      });
    }
    return {
      totalConnections: this.connections.size,
      connections,
    };
  }

  /**
   * Broadcast a message to all connected clients.
   * Useful for server-initiated messages.
   */
  broadcast(data: unknown, filter?: (state: ConnectionState) => boolean): void {
    for (const [ws, state] of this.connections) {
      if (!filter || filter(state)) {
        this.send(ws, data);
      }
    }
  }

  /**
   * Get all authenticated connections for a specific user.
   */
  getAuthenticatedConnections(userId: string): WebSocket[] {
    const result: WebSocket[] = [];
    for (const [ws, state] of this.connections) {
      if (state.authenticated && state.userId === userId) {
        result.push(ws);
      }
    }
    return result;
  }
}
