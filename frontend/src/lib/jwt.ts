/**
 * Reads the `exp` claim of the CCMS access token so the UI can end the session
 * when it expires. This is NOT verification — the backend verifies every token;
 * the client only uses `exp` to avoid showing a session that is already dead.
 */
export function readTokenExpiry(token: string): number | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded)) as { exp?: unknown };
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string, now: number = Date.now()): boolean {
  const expiry = readTokenExpiry(token);
  return expiry !== null && expiry <= now;
}
