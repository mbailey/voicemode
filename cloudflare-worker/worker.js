/**
 * VoiceMode Telemetry Endpoint
 *
 * Cloudflare Worker that receives telemetry events from VoiceMode clients.
 *
 * Features:
 * - Payload validation
 * - Rate limiting per anonymous ID (10 events/hour)
 * - Rate limiting per IP (100 events/hour)
 * - Idempotency via event_id
 * - Storage in D1 database
 * - CORS support
 */

// Rate limit windows (in seconds)
const RATE_LIMIT_WINDOW = 3600; // 1 hour
const ID_RATE_LIMIT = 10; // max events per telemetry_id per hour
const IP_RATE_LIMIT = 100; // max events per IP per hour

// Event retention period
const EVENT_RETENTION_DAYS = 90;

export default {
  async fetch(request, env, ctx) {
    // Handle CORS preflight requests
    if (request.method === "OPTIONS") {
      return handleCORS();
    }

    // Only accept POST requests to /telemetry
    if (request.method !== "POST" || !request.url.endsWith('/telemetry')) {
      return new Response('Not Found', {
        status: 404,
        headers: getCORSHeaders()
      });
    }

    try {
      // Parse and validate payload
      const payload = await request.json();
      const validationError = validatePayload(payload);
      if (validationError) {
        return new Response(JSON.stringify({ error: validationError }), {
          status: 400,
          headers: {
            'Content-Type': 'application/json',
            ...getCORSHeaders()
          }
        });
      }

      // Extract client info
      const clientIP = request.headers.get('CF-Connecting-IP') || 'unknown';
      const telemetryId = payload.telemetry_id;
      const eventId = payload.event_id;

      // Check idempotency - has this event been seen before?
      const isDuplicate = await checkEventExists(env.DB, eventId);
      if (isDuplicate) {
        // Return success for idempotency - client doesn't need to retry
        return new Response(JSON.stringify({
          status: 'ok',
          message: 'Event already recorded'
        }), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            ...getCORSHeaders()
          }
        });
      }

      // Check rate limits
      const idRateLimitExceeded = await checkRateLimit(
        env.KV,
        `rate:id:${telemetryId}`,
        ID_RATE_LIMIT
      );

      if (idRateLimitExceeded) {
        return new Response(JSON.stringify({
          error: 'Rate limit exceeded for telemetry ID',
          retry_after: RATE_LIMIT_WINDOW
        }), {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': RATE_LIMIT_WINDOW.toString(),
            ...getCORSHeaders()
          }
        });
      }

      const ipHash = await hashIP(clientIP);
      const ipRateLimitExceeded = await checkRateLimit(
        env.KV,
        `rate:ip:${ipHash}`,
        IP_RATE_LIMIT
      );

      if (ipRateLimitExceeded) {
        return new Response(JSON.stringify({
          error: 'Rate limit exceeded for IP address',
          retry_after: RATE_LIMIT_WINDOW
        }), {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': RATE_LIMIT_WINDOW.toString(),
            ...getCORSHeaders()
          }
        });
      }

      // Store the event in D1
      await storeEvent(env.DB, payload, clientIP);

      // Increment rate limit counters
      await incrementRateLimit(env.KV, `rate:id:${telemetryId}`);
      await incrementRateLimit(env.KV, `rate:ip:${ipHash}`);

      // Return success
      return new Response(JSON.stringify({
        status: 'ok',
        event_id: eventId
      }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          ...getCORSHeaders()
        }
      });

    } catch (error) {
      console.error('Error processing telemetry:', error);

      return new Response(JSON.stringify({
        error: 'Internal server error',
        message: error.message
      }), {
        status: 500,
        headers: {
          'Content-Type': 'application/json',
          ...getCORSHeaders()
        }
      });
    }
  },

  // Scheduled handler for cleanup tasks
  async scheduled(event, env, ctx) {
    // Clean up old events (beyond retention period)
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - EVENT_RETENTION_DAYS);

    try {
      await env.DB.prepare(
        'DELETE FROM events WHERE created_at < ?'
      ).bind(cutoffDate.toISOString()).run();

      console.log(`Cleaned up events older than ${EVENT_RETENTION_DAYS} days`);
    } catch (error) {
      console.error('Error during cleanup:', error);
    }
  }
};

/**
 * Validate telemetry payload structure.
 *
 * Expected structure:
 * {
 *   "event_id": "string",
 *   "telemetry_id": "string (UUID)",
 *   "timestamp": "ISO 8601 datetime string",
 *   "environment": {
 *     "os": "string",
 *     "version": "string",
 *     "installation_method": "string",
 *     "mcp_host": "string",
 *     "execution_source": "string"
 *   },
 *   "usage": {
 *     "total_sessions": number,
 *     "duration_distribution": {...},
 *     "transport_usage": {...},
 *     "provider_usage": {...}
 *   }
 * }
 */
function validatePayload(payload) {
  if (!payload) {
    return 'Missing payload';
  }

  // Required top-level fields
  if (!payload.event_id || typeof payload.event_id !== 'string') {
    return 'Invalid or missing event_id';
  }

  if (!payload.telemetry_id || typeof payload.telemetry_id !== 'string') {
    return 'Invalid or missing telemetry_id';
  }

  // Validate telemetry_id is a valid UUID format
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!uuidRegex.test(payload.telemetry_id)) {
    return 'Invalid telemetry_id format (must be UUID)';
  }

  if (!payload.timestamp || typeof payload.timestamp !== 'string') {
    return 'Invalid or missing timestamp';
  }

  // Validate timestamp is valid ISO 8601
  const timestamp = new Date(payload.timestamp);
  if (isNaN(timestamp.getTime())) {
    return 'Invalid timestamp format (must be ISO 8601)';
  }

  // Validate timestamp is not too far in the future or past
  const now = new Date();
  const dayInMs = 86400000;
  if (timestamp > new Date(now.getTime() + dayInMs)) {
    return 'Timestamp too far in the future';
  }
  if (timestamp < new Date(now.getTime() - (90 * dayInMs))) {
    return 'Timestamp too old (max 90 days)';
  }

  // Required: environment object
  if (!payload.environment || typeof payload.environment !== 'object') {
    return 'Invalid or missing environment object';
  }

  const env = payload.environment;
  if (!env.os || typeof env.os !== 'string') {
    return 'Invalid or missing environment.os';
  }
  if (!env.version || typeof env.version !== 'string') {
    return 'Invalid or missing environment.version';
  }

  // Required: usage object
  if (!payload.usage || typeof payload.usage !== 'object') {
    return 'Invalid or missing usage object';
  }

  const usage = payload.usage;
  if (typeof usage.total_sessions !== 'number') {
    return 'Invalid or missing usage.total_sessions';
  }

  // All validation passed
  return null;
}

/**
 * Check if an event already exists in the database.
 */
async function checkEventExists(db, eventId) {
  const result = await db.prepare(
    'SELECT event_id FROM events WHERE event_id = ? LIMIT 1'
  ).bind(eventId).first();

  return result !== null;
}

/**
 * Check rate limit for a given key.
 */
async function checkRateLimit(kv, key, limit) {
  const count = await kv.get(key);
  if (!count) {
    return false; // No previous requests
  }

  return parseInt(count) >= limit;
}

/**
 * Increment rate limit counter.
 */
async function incrementRateLimit(kv, key) {
  const current = await kv.get(key);
  const newCount = current ? parseInt(current) + 1 : 1;

  // Store with TTL equal to the rate limit window
  await kv.put(key, newCount.toString(), {
    expirationTtl: RATE_LIMIT_WINDOW
  });
}

/**
 * Store telemetry event in D1 database.
 */
async function storeEvent(db, payload, clientIP) {
  const hashedIP = await hashIP(clientIP);

  await db.prepare(`
    INSERT INTO events (
      event_id,
      telemetry_id,
      timestamp,
      environment,
      usage,
      client_ip_hash,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(
    payload.event_id,
    payload.telemetry_id,
    payload.timestamp,
    JSON.stringify(payload.environment),
    JSON.stringify(payload.usage),
    hashedIP,
    new Date().toISOString()
  ).run();
}

/**
 * Hash IP address for privacy.
 * Uses SHA-256 to anonymize while maintaining ability to rate limit.
 */
async function hashIP(ip) {
  const encoder = new TextEncoder();
  const data = encoder.encode(ip);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  return hashHex.substring(0, 16); // Use first 16 chars
}

/**
 * Get CORS headers.
 */
function getCORSHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}

/**
 * Handle CORS preflight requests.
 */
function handleCORS() {
  return new Response(null, {
    status: 204,
    headers: getCORSHeaders()
  });
}
