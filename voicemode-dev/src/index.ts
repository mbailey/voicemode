/**
 * VoiceMode.dev Cloudflare Worker
 *
 * Main entry point for the voicemode.dev service.
 * Routes requests to appropriate handlers:
 * - /ws/* -> WebSocket Gateway (Durable Objects)
 * - /health -> Health check
 * - /mcp/* -> MCP server (future)
 * - /auth/* -> OAuth/Auth0 (future)
 */

import { WebSocketGateway } from "./durable-objects/websocket-gateway";

export interface Env {
  WEBSOCKET_GATEWAY: DurableObjectNamespace;
  ENVIRONMENT: string;
  AUTH0_DOMAIN?: string;
  AUTH0_CLIENT_ID?: string;
  AUTH0_CLIENT_SECRET?: string;
  AUTH0_AUDIENCE?: string;
}

// Export the Durable Object class so Cloudflare can find it
export { WebSocketGateway };

export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    const url = new URL(request.url);

    // CORS headers for all responses
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };

    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      // Route based on path
      if (url.pathname === "/" || url.pathname === "/health") {
        return handleHealth(env, corsHeaders);
      }

      if (url.pathname.startsWith("/ws")) {
        return handleWebSocket(request, env, url);
      }

      // Future routes:
      // if (url.pathname.startsWith("/mcp")) {
      //   return handleMcp(request, env);
      // }
      // if (url.pathname.startsWith("/auth")) {
      //   return handleAuth(request, env);
      // }

      return new Response("Not Found", {
        status: 404,
        headers: corsHeaders,
      });
    } catch (error) {
      console.error("[Worker] Error:", error);
      return new Response(
        JSON.stringify({
          error: "Internal Server Error",
          message: error instanceof Error ? error.message : "Unknown error",
        }),
        {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }
  },
};

/**
 * Handle health check requests.
 */
function handleHealth(
  env: Env,
  corsHeaders: Record<string, string>
): Response {
  return new Response(
    JSON.stringify({
      status: "ok",
      service: "voicemode.dev",
      version: "0.1.0",
      environment: env.ENVIRONMENT,
      timestamp: new Date().toISOString(),
      features: {
        websocket: true,
        mcp: false, // Coming in ws-003
        auth: false, // Coming in ws-002
      },
    }),
    {
      headers: {
        ...corsHeaders,
        "Content-Type": "application/json",
      },
    }
  );
}

/**
 * Handle WebSocket requests.
 * Routes to the appropriate Durable Object based on the path.
 *
 * Path format: /ws/{userId} or /ws (for unauthenticated testing)
 *
 * The userId determines which Durable Object handles the connection.
 * This allows each user to have their own isolated connection state.
 */
async function handleWebSocket(
  request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  // Extract user ID from path or query param (for testing)
  // In production, this would come from JWT validation
  const pathParts = url.pathname.split("/").filter(Boolean);
  const userId = pathParts[1] || url.searchParams.get("user") || "anonymous";

  // Check for WebSocket upgrade
  if (request.headers.get("Upgrade") !== "websocket") {
    // Return info about the WebSocket endpoint
    return new Response(
      JSON.stringify({
        endpoint: "/ws",
        description: "WebSocket endpoint for VoiceMode mobile app connections",
        protocol: "wss",
        usage: {
          connect: "wss://voicemode.dev/ws?token=<jwt>",
          messages: {
            heartbeat: "Send { type: 'heartbeat' } to keep connection alive",
            ping: "Send { type: 'ping' } to measure latency",
          },
        },
      }),
      {
        headers: { "Content-Type": "application/json" },
      }
    );
  }

  console.log(`[Worker] WebSocket request for user: ${userId}`);

  // Get or create the Durable Object for this user
  // Using the user ID as the key ensures all connections for a user
  // go to the same Durable Object instance
  const durableObjectId = env.WEBSOCKET_GATEWAY.idFromName(userId);
  const durableObject = env.WEBSOCKET_GATEWAY.get(durableObjectId);

  // Forward the request to the Durable Object
  return durableObject.fetch(request);
}
