/**
 * Web Crypto PKCE & Verifier Utilities
 * Implements S256 challenge creation using standard browser Web Crypto APIs.
 */

function base64UrlEncode(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/**
 * Generates a cryptographically random verifier string in memory.
 * Never persisted in localStorage or cookies.
 */
export function generatePkceVerifier(length = 48): string {
  const randomBytes = new Uint8Array(length);
  window.crypto.getRandomValues(randomBytes);
  return base64UrlEncode(randomBytes);
}

/**
 * Computes SHA-256 base64url challenge from the verifier string.
 */
export async function generatePkceChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await window.crypto.subtle.digest('SHA-256', data);
  return base64UrlEncode(digest);
}
