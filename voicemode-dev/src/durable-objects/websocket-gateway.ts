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

export interface Env {
  WEBSOCKET_GATEWAY: DurableObjectNamespace;
  ENVIRONMENT: string;
}

/** Connection state for a WebSocket client */
interface ConnectionState {
  /** WebSocket connection */
  websocket: WebSocket;
  /** User ID from JWT token */
  userId: string | null;
  /** Whether the connection is authenticated */
  authenticated: boolean;
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
}

export class WebSocketGateway extends DurableObject {
  /** Active connections (a user may have multiple devices) */
  private connections: Map<WebSocket, ConnectionState> = new Map();

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
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
   */
  private async handleWebSocketUpgrade(request: Request): Promise<Response> {
    // Create WebSocket pair (client and server sides)
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);

    // Accept the WebSocket connection on the server side
    this.ctx.acceptWebSocket(server);

    // Initialize connection state (not yet authenticated)
    const state: ConnectionState = {
      websocket: server,
      userId: null,
      authenticated: false,
      ready: false,
      lastActivity: Date.now(),
      connectedAt: Date.now(),
    };
    this.connections.set(server, state);

    console.log(
      `[WebSocketGateway] New connection. Total: ${this.connections.size}`
    );

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

    // Parse message (expect JSON)
    let data: unknown;
    try {
      const msgStr =
        typeof message === "string"
          ? message
          : new TextDecoder().decode(message);
      data = JSON.parse(msgStr);
    } catch (e) {
      this.sendError(ws, "PARSE_ERROR", "Invalid JSON message");
      return;
    }

    // Handle message based on type
    if (typeof data === "object" && data !== null && "type" in data) {
      const msg = data as { type: string; [key: string]: unknown };
      await this.handleMessage(ws, state, msg);
    } else {
      this.sendError(ws, "INVALID_MESSAGE", "Message must have a type field");
    }
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
      console.log(
        `[WebSocketGateway] Connection closed. User: ${state.userId}, Code: ${code}, Reason: ${reason}`
      );
      this.connections.delete(ws);
    }
    console.log(
      `[WebSocketGateway] Connection removed. Total: ${this.connections.size}`
    );
  }

  /**
   * Handle WebSocket error event.
   */
  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    const state = this.connections.get(ws);
    console.error(
      `[WebSocketGateway] WebSocket error. User: ${state?.userId}`,
      error
    );
    this.connections.delete(ws);
  }

  /**
   * Handle a typed message from a client.
   */
  private async handleMessage(
    ws: WebSocket,
    state: ConnectionState,
    msg: { type: string; [key: string]: unknown }
  ): Promise<void> {
    console.log(
      `[WebSocketGateway] Message type: ${msg.type}, authenticated: ${state.authenticated}`
    );

    switch (msg.type) {
      case "heartbeat":
        // Respond to heartbeat immediately
        this.send(ws, { type: "heartbeat_ack", timestamp: Date.now() });
        break;

      case "ping":
        // Simple ping/pong for latency measurement
        this.send(ws, { type: "pong", timestamp: Date.now() });
        break;

      default:
        // For now, echo unknown messages for testing
        // In production, this would be handled by specific message handlers
        console.log(`[WebSocketGateway] Unhandled message type: ${msg.type}`);
        this.send(ws, {
          type: "echo",
          original: msg,
          timestamp: Date.now(),
        });
    }
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
        ready: state.ready,
        connectedAt: state.connectedAt,
        lastActivity: state.lastActivity,
        deviceInfo: state.deviceInfo,
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
