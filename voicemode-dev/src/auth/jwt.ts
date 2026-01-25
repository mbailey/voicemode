/**
 * JWT Validation for Auth0
 *
 * Validates JWT tokens issued by Auth0 for WebSocket authentication.
 * Uses Auth0's JWKS endpoint to fetch public keys for signature verification.
 */

export interface JWTPayload {
  /** Subject (user ID) */
  sub: string;
  /** Issuer (Auth0 domain) */
  iss: string;
  /** Audience */
  aud: string | string[];
  /** Expiration time (Unix timestamp) */
  exp: number;
  /** Issued at time (Unix timestamp) */
  iat: number;
  /** Email (if available) */
  email?: string;
  /** Email verified */
  email_verified?: boolean;
  /** Name (if available) */
  name?: string;
  /** Picture URL (if available) */
  picture?: string;
  /** Additional custom claims */
  [key: string]: unknown;
}

export interface JWTValidationResult {
  valid: boolean;
  payload?: JWTPayload;
  error?: string;
  errorCode?: 'INVALID_TOKEN' | 'EXPIRED_TOKEN' | 'INVALID_SIGNATURE' | 'INVALID_CLAIMS' | 'JWKS_ERROR';
}

export interface JWTValidationOptions {
  /** Auth0 domain (e.g., 'your-tenant.auth0.com') */
  domain: string;
  /** Expected audience (API identifier) */
  audience: string;
  /** Clock skew tolerance in seconds (default: 60) */
  clockTolerance?: number;
}

/** JWKS key structure */
interface JWK {
  kty: string;
  use?: string;
  kid: string;
  n: string;
  e: string;
  alg?: string;
}

interface JWKS {
  keys: JWK[];
}

/** In-memory cache for JWKS keys */
const jwksCache = new Map<string, { keys: JWKS; fetchedAt: number }>();
const JWKS_CACHE_TTL = 3600000; // 1 hour in milliseconds

/**
 * Fetch JWKS (JSON Web Key Set) from Auth0.
 * Caches the result for 1 hour.
 */
async function fetchJWKS(domain: string): Promise<JWKS> {
  const cacheKey = domain;
  const cached = jwksCache.get(cacheKey);

  if (cached && Date.now() - cached.fetchedAt < JWKS_CACHE_TTL) {
    return cached.keys;
  }

  const jwksUrl = `https://${domain}/.well-known/jwks.json`;

  try {
    const response = await fetch(jwksUrl);
    if (!response.ok) {
      throw new Error(`Failed to fetch JWKS: ${response.status}`);
    }

    const jwks = await response.json() as JWKS;
    jwksCache.set(cacheKey, { keys: jwks, fetchedAt: Date.now() });
    return jwks;
  } catch (error) {
    console.error('[JWT] Failed to fetch JWKS:', error);
    throw error;
  }
}

/**
 * Decode a base64url-encoded string.
 */
function base64UrlDecode(str: string): Uint8Array {
  // Replace base64url chars with base64 chars
  const base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  // Pad to multiple of 4
  const padded = base64.padEnd(base64.length + (4 - base64.length % 4) % 4, '=');
  // Decode
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Parse JWT header to get the key ID (kid).
 */
function parseJWTHeader(token: string): { alg: string; kid?: string } {
  const parts = token.split('.');
  if (parts.length !== 3) {
    throw new Error('Invalid JWT format');
  }

  const headerJson = new TextDecoder().decode(base64UrlDecode(parts[0]));
  return JSON.parse(headerJson);
}

/**
 * Parse JWT payload without verification.
 */
function parseJWTPayload(token: string): JWTPayload {
  const parts = token.split('.');
  if (parts.length !== 3) {
    throw new Error('Invalid JWT format');
  }

  const payloadJson = new TextDecoder().decode(base64UrlDecode(parts[1]));
  return JSON.parse(payloadJson);
}

/**
 * Import a JWK as a CryptoKey for signature verification.
 */
async function importJWK(jwk: JWK): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'jwk',
    {
      kty: jwk.kty,
      n: jwk.n,
      e: jwk.e,
      alg: jwk.alg || 'RS256',
      use: 'sig',
    },
    {
      name: 'RSASSA-PKCS1-v1_5',
      hash: 'SHA-256',
    },
    false,
    ['verify']
  );
}

/**
 * Verify JWT signature using the JWKS.
 */
async function verifySignature(token: string, jwks: JWKS): Promise<boolean> {
  const parts = token.split('.');
  if (parts.length !== 3) {
    return false;
  }

  const header = parseJWTHeader(token);
  const kid = header.kid;

  // Find the matching key
  const jwk = jwks.keys.find(k => k.kid === kid);
  if (!jwk) {
    console.error(`[JWT] No matching key found for kid: ${kid}`);
    return false;
  }

  try {
    const key = await importJWK(jwk);
    const signature = base64UrlDecode(parts[2]);
    const data = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);

    return crypto.subtle.verify(
      'RSASSA-PKCS1-v1_5',
      key,
      signature,
      data
    );
  } catch (error) {
    console.error('[JWT] Signature verification failed:', error);
    return false;
  }
}

/**
 * Validate a JWT token against Auth0.
 */
export async function validateJWT(
  token: string,
  options: JWTValidationOptions
): Promise<JWTValidationResult> {
  const clockTolerance = options.clockTolerance ?? 60;

  try {
    // Parse the token
    let payload: JWTPayload;
    try {
      payload = parseJWTPayload(token);
    } catch (e) {
      return {
        valid: false,
        error: 'Invalid token format',
        errorCode: 'INVALID_TOKEN',
      };
    }

    // Check expiration
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && payload.exp < now - clockTolerance) {
      return {
        valid: false,
        error: 'Token has expired',
        errorCode: 'EXPIRED_TOKEN',
      };
    }

    // Check issuer
    const expectedIssuer = `https://${options.domain}/`;
    if (payload.iss !== expectedIssuer) {
      return {
        valid: false,
        error: `Invalid issuer: expected ${expectedIssuer}, got ${payload.iss}`,
        errorCode: 'INVALID_CLAIMS',
      };
    }

    // Check audience
    const audiences = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
    if (!audiences.includes(options.audience)) {
      return {
        valid: false,
        error: `Invalid audience: expected ${options.audience}`,
        errorCode: 'INVALID_CLAIMS',
      };
    }

    // Fetch JWKS and verify signature
    let jwks: JWKS;
    try {
      jwks = await fetchJWKS(options.domain);
    } catch (e) {
      return {
        valid: false,
        error: 'Failed to fetch JWKS for signature verification',
        errorCode: 'JWKS_ERROR',
      };
    }

    const signatureValid = await verifySignature(token, jwks);
    if (!signatureValid) {
      return {
        valid: false,
        error: 'Invalid token signature',
        errorCode: 'INVALID_SIGNATURE',
      };
    }

    // Token is valid
    return {
      valid: true,
      payload,
    };
  } catch (error) {
    console.error('[JWT] Validation error:', error);
    return {
      valid: false,
      error: error instanceof Error ? error.message : 'Unknown error',
      errorCode: 'INVALID_TOKEN',
    };
  }
}

/**
 * Extract user information from a validated JWT payload.
 */
export function extractUserInfo(payload: JWTPayload): {
  userId: string;
  email?: string;
  name?: string;
  picture?: string;
} {
  return {
    userId: payload.sub,
    email: payload.email,
    name: payload.name,
    picture: payload.picture,
  };
}
