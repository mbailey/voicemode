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
import { validateJWT, extractUserInfo, JWTPayload } from "./auth/jwt";

export interface Env {
  WEBSOCKET_GATEWAY: DurableObjectNamespace;
  ENVIRONMENT: string;
  AUTH0_DOMAIN?: string;
  AUTH0_CLIENT_ID?: string;
  AUTH0_CLIENT_SECRET?: string;
  AUTH0_AUDIENCE?: string;
}

/** Validated user info passed to WebSocket handler */
interface AuthenticatedUser {
  userId: string;
  email?: string;
  name?: string;
  picture?: string;
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
        auth: true, // JWT validation enabled
      },
      auth: {
        provider: "auth0",
        configured: !!(env.AUTH0_DOMAIN && env.AUTH0_AUDIENCE),
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
 * Authentication: JWT token must be provided in query param: wss://...?token=<jwt>
 *
 * The userId (from JWT) determines which Durable Object handles the connection.
 * This allows each user to have their own isolated connection state.
 */
async function handleWebSocket(
  request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  // Check for WebSocket upgrade
  if (request.headers.get("Upgrade") !== "websocket") {
    // Return info about the WebSocket endpoint
    return new Response(
      JSON.stringify({
        endpoint: "/ws",
        description: "WebSocket endpoint for VoiceMode mobile app connections",
        protocol: "wss",
        authentication: "JWT token required in query param",
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

  // Extract JWT token from query param
  const token = url.searchParams.get("token");

  // Check if Auth0 is configured
  const auth0Configured = env.AUTH0_DOMAIN && env.AUTH0_AUDIENCE;

  let authenticatedUser: AuthenticatedUser | null = null;

  if (token && auth0Configured) {
    // Validate JWT token against Auth0
    console.log(`[Worker] Validating JWT token...`);
    const validationResult = await validateJWT(token, {
      domain: env.AUTH0_DOMAIN!,
      audience: env.AUTH0_AUDIENCE!,
    });

    if (!validationResult.valid) {
      console.log(`[Worker] JWT validation failed: ${validationResult.error}`);
      return new Response(
        JSON.stringify({
          error: "Authentication failed",
          code: validationResult.errorCode,
          message: validationResult.error,
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    // Extract user info from validated token
    authenticatedUser = extractUserInfo(validationResult.payload!);
    console.log(`[Worker] JWT validated for user: ${authenticatedUser.userId}`);
  } else if (token && !auth0Configured) {
    // Token provided but Auth0 not configured - reject in production
    if (env.ENVIRONMENT === "production") {
      return new Response(
        JSON.stringify({
          error: "Authentication not configured",
          message: "Auth0 credentials are not configured on the server",
        }),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }
      );
    }
    // In development, allow connection but log warning
    console.warn(`[Worker] Token provided but Auth0 not configured. Allowing connection in ${env.ENVIRONMENT} mode.`);
  } else if (!token) {
    // No token provided
    if (env.ENVIRONMENT === "production" || auth0Configured) {
      console.log(`[Worker] No token provided, rejecting connection`);
      return new Response(
        JSON.stringify({
          error: "Authentication required",
          message: "JWT token must be provided in query param: ?token=<jwt>",
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }
      );
    }
    // In development without Auth0 configured, allow anonymous connections
    console.warn(`[Worker] No token provided. Allowing anonymous connection in ${env.ENVIRONMENT} mode.`);
  }

  // Determine user ID for Durable Object routing
  // Use authenticated user ID if available, otherwise fall back for development
  const userId = authenticatedUser?.userId ||
    url.searchParams.get("user") ||
    "anonymous-dev";

  console.log(`[Worker] WebSocket request for user: ${userId}, authenticated: ${!!authenticatedUser}`);

  // Get or create the Durable Object for this user
  // Using the user ID as the key ensures all connections for a user
  // go to the same Durable Object instance
  const durableObjectId = env.WEBSOCKET_GATEWAY.idFromName(userId);
  const durableObject = env.WEBSOCKET_GATEWAY.get(durableObjectId);

  // Create a new request with user info header for the Durable Object
  const headers = new Headers(request.headers);
  if (authenticatedUser) {
    headers.set("X-Authenticated-User", JSON.stringify(authenticatedUser));
  }

  const authenticatedRequest = new Request(request.url, {
    method: request.method,
    headers,
    body: request.body,
  });

  // Forward the request to the Durable Object
  return durableObject.fetch(authenticatedRequest);
}
