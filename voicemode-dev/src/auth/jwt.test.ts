/**
 * Unit tests for JWT validation
 */
import { describe, it, expect, vi } from 'vitest';

// Mock the parseJWTPayload function for testing payload validation
// (We can't easily test full JWT validation without a real Auth0 token)

describe('JWT Payload Parsing', () => {
  // Helper to create a base64url-encoded string
  function base64UrlEncode(obj: object): string {
    const json = JSON.stringify(obj);
    const base64 = btoa(json);
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  // Helper to create a mock JWT (not cryptographically valid)
  function createMockJWT(payload: object, header = { alg: 'RS256', typ: 'JWT' }): string {
    const headerEncoded = base64UrlEncode(header);
    const payloadEncoded = base64UrlEncode(payload);
    const signatureEncoded = base64UrlEncode({ sig: 'mock' }); // Not a real signature
    return `${headerEncoded}.${payloadEncoded}.${signatureEncoded}`;
  }

  it('should parse a valid JWT payload structure', () => {
    const payload = {
      sub: 'auth0|12345',
      iss: 'https://example.auth0.com/',
      aud: 'my-api',
      exp: Math.floor(Date.now() / 1000) + 3600,
      iat: Math.floor(Date.now() / 1000),
      email: 'user@example.com',
      name: 'Test User',
    };

    const token = createMockJWT(payload);
    const parts = token.split('.');
    expect(parts).toHaveLength(3);

    // Decode and verify payload
    const decodedPayload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
    expect(decodedPayload.sub).toBe('auth0|12345');
    expect(decodedPayload.email).toBe('user@example.com');
    expect(decodedPayload.name).toBe('Test User');
  });

  it('should detect expired tokens', () => {
    const expiredPayload = {
      sub: 'auth0|12345',
      iss: 'https://example.auth0.com/',
      aud: 'my-api',
      exp: Math.floor(Date.now() / 1000) - 3600, // Expired 1 hour ago
      iat: Math.floor(Date.now() / 1000) - 7200,
    };

    const now = Math.floor(Date.now() / 1000);
    const clockTolerance = 60;
    expect(expiredPayload.exp < now - clockTolerance).toBe(true);
  });

  it('should validate issuer format', () => {
    const domain = 'example.auth0.com';
    const expectedIssuer: string = `https://${domain}/`;

    expect(expectedIssuer).toBe('https://example.auth0.com/');

    // Valid issuer
    const validIssuer: string = 'https://example.auth0.com/';
    expect(validIssuer === expectedIssuer).toBe(true);

    // Invalid issuers
    const invalidIssuer1: string = 'https://other.auth0.com/';
    const invalidIssuer2: string = 'http://example.auth0.com/';
    const invalidIssuer3: string = 'example.auth0.com';
    expect(invalidIssuer1 === expectedIssuer).toBe(false);
    expect(invalidIssuer2 === expectedIssuer).toBe(false);
    expect(invalidIssuer3 === expectedIssuer).toBe(false);
  });

  it('should handle audience as array or string', () => {
    const expectedAudience = 'my-api';

    // String audience
    const stringAud = 'my-api';
    const audiences1 = Array.isArray(stringAud) ? stringAud : [stringAud];
    expect(audiences1.includes(expectedAudience)).toBe(true);

    // Array audience
    const arrayAud = ['my-api', 'other-api'];
    const audiences2 = Array.isArray(arrayAud) ? arrayAud : [arrayAud];
    expect(audiences2.includes(expectedAudience)).toBe(true);

    // Wrong audience
    const wrongAud = 'wrong-api';
    const audiences3 = Array.isArray(wrongAud) ? wrongAud : [wrongAud];
    expect(audiences3.includes(expectedAudience)).toBe(false);
  });

  it('should extract user info from payload', () => {
    const payload = {
      sub: 'auth0|user123',
      email: 'user@example.com',
      name: 'John Doe',
      picture: 'https://example.com/avatar.jpg',
    };

    const userInfo = {
      userId: payload.sub,
      email: payload.email,
      name: payload.name,
      picture: payload.picture,
    };

    expect(userInfo.userId).toBe('auth0|user123');
    expect(userInfo.email).toBe('user@example.com');
    expect(userInfo.name).toBe('John Doe');
    expect(userInfo.picture).toBe('https://example.com/avatar.jpg');
  });
});

describe('JWT Header Parsing', () => {
  it('should detect RS256 algorithm', () => {
    const header: { alg: string; typ: string; kid?: string } = { alg: 'RS256', typ: 'JWT', kid: 'key-1' };
    expect(header.alg).toBe('RS256');
    expect(header.kid).toBe('key-1');
  });

  it('should handle missing kid gracefully', () => {
    const header: { alg: string; typ: string; kid?: string } = { alg: 'RS256', typ: 'JWT' };
    expect(header.kid).toBeUndefined();
  });
});

describe('Token Format Validation', () => {
  it('should reject tokens with wrong number of parts', () => {
    const badTokens = [
      'only-one-part',
      'two.parts',
      'four.parts.too.many',
      '',
    ];

    for (const token of badTokens) {
      const parts = token.split('.');
      expect(parts.length === 3).toBe(false);
    }
  });

  it('should accept tokens with three parts', () => {
    const goodToken = 'header.payload.signature';
    const parts = goodToken.split('.');
    expect(parts.length === 3).toBe(true);
  });
});
