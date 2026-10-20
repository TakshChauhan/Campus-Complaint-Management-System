import { describe, expect, it, vi } from 'vitest';
import { apiRequest, apiUrl, normalizeApiBase, setStoredToken, UNAUTHORIZED_EVENT, getStoredToken } from '../api/client';
import { isSafeInternalPath, matchPath } from '../lib/router';
import { generatePkceChallenge, generatePkceVerifier } from '../utils/crypto';
import { homePathForRole, isTrustedGoogleMessage } from '../context/AuthContext';
import { isTokenExpired, readTokenExpiry } from '../lib/jwt';
import { makeToken, mockApi } from './mockApi';

describe('API base URL handling', () => {
  it('never duplicates /api/v1', () => {
    expect(normalizeApiBase('http://localhost:8000')).toBe('http://localhost:8000');
    expect(normalizeApiBase('http://localhost:8000/')).toBe('http://localhost:8000');
    expect(normalizeApiBase('http://localhost:8000/api/v1')).toBe('http://localhost:8000');
    expect(normalizeApiBase('https://api.example.edu/api/v1/')).toBe('https://api.example.edu');
    expect(normalizeApiBase('')).toBe('http://localhost:8000');
    expect(normalizeApiBase(undefined)).toBe('http://localhost:8000');
  });

  it('builds versioned and root URLs', () => {
    expect(apiUrl('/complaints')).toMatch(/\/api\/v1\/complaints$/);
    expect(apiUrl('/health', { versioned: false })).toMatch(/[^1]\/health$/);
    expect(apiUrl('/complaints')).not.toContain('/api/v1/api/v1');
  });
});

describe('401 handling', () => {
  it('broadcasts session end only for requests that carried a token', async () => {
    mockApi({ 'POST /api/v1/auth/login': () => ({ status: 401, body: { detail: 'Invalid email or password.' } }) });
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);

    await expect(apiRequest('/auth/login', { method: 'POST', body: {}, auth: false })).rejects.toMatchObject({ status: 401 });
    expect(listener).not.toHaveBeenCalled();

    mockApi({ 'GET /api/v1/users/me': () => ({ status: 401, body: { detail: 'expired' } }) });
    setStoredToken(makeToken());
    await expect(apiRequest('/users/me')).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getStoredToken()).toBeNull();
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
  });

  it('turns network failures into a readable error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    await expect(apiRequest('/departments')).rejects.toMatchObject({ status: 0, message: expect.stringContaining("Can't reach") });
  });
});

describe('router safety', () => {
  it('accepts only internal paths', () => {
    expect(isSafeInternalPath('/complaints?page=2')).toBe(true);
    expect(isSafeInternalPath('//evil.example')).toBe(false);
    expect(isSafeInternalPath('/\\evil.example')).toBe(false);
    expect(isSafeInternalPath('https://evil.example')).toBe(false);
    expect(isSafeInternalPath('javascript:alert(1)')).toBe(false);
    expect(isSafeInternalPath(42)).toBe(false);
  });

  it('matches params', () => {
    expect(matchPath('/complaints/:id', '/complaints/12')).toEqual({ id: '12' });
    expect(matchPath('/complaints/:id', '/complaints')).toBeNull();
    expect(matchPath('/complaints', '/complaints/')).toEqual({});
  });
});

describe('PKCE', () => {
  it('matches the RFC 7636 S256 test vector', async () => {
    await expect(generatePkceChallenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk')).resolves.toBe(
      'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    );
  });

  it('generates distinct base64url verifiers of RFC length', () => {
    const a = generatePkceVerifier();
    const b = generatePkceVerifier();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9_-]{43,128}$/);
  });
});

describe('Google popup message validation', () => {
  const popup = {} as Window;
  const api = 'http://localhost:8000';
  const app = 'http://localhost:5173';
  const ok = { type: 'CCMS_GOOGLE_AUTH_SUCCESS', ticket: 't' };

  it('accepts the popup message from the API origin', () => {
    expect(isTrustedGoogleMessage({ origin: api, source: popup, data: ok }, popup, api, app)).toBe(true);
  });
  it('rejects other origins', () => {
    expect(isTrustedGoogleMessage({ origin: 'https://evil.example', source: popup, data: ok }, popup, api, app)).toBe(false);
  });
  it('rejects other windows', () => {
    expect(isTrustedGoogleMessage({ origin: api, source: {} as Window, data: ok }, popup, api, app)).toBe(false);
  });
  it('rejects unknown message types', () => {
    expect(isTrustedGoogleMessage({ origin: api, source: popup, data: { type: 'x' } }, popup, api, app)).toBe(false);
  });
});

describe('roles and tokens', () => {
  it('maps each role to its home page', () => {
    expect(homePathForRole('student')).toBe('/dashboard');
    expect(homePathForRole('staff')).toBe('/staff');
    expect(homePathForRole('admin')).toBe('/admin');
  });

  it('reads exp and detects expiry', () => {
    const live = makeToken(600);
    expect(readTokenExpiry(live)).toBeGreaterThan(Date.now());
    expect(isTokenExpired(live)).toBe(false);
    expect(isTokenExpired(makeToken(-10))).toBe(true);
    expect(readTokenExpiry('not-a-jwt')).toBeNull();
  });
});

describe('post-login destination', () => {
  it('returns to an allowed page and ignores pages the role cannot open', async () => {
    const { postLoginPath } = await import('../lib/access');
    expect(postLoginPath('/complaints?page=2', 'student', '/dashboard')).toBe('/complaints?page=2');
    expect(postLoginPath('/dashboard', 'staff', '/staff')).toBe('/staff');
    expect(postLoginPath('/profile', 'admin', '/admin')).toBe('/profile');
    expect(postLoginPath('//evil.example', 'student', '/dashboard')).toBe('/dashboard');
    expect(postLoginPath('/login', 'student', '/dashboard')).toBe('/dashboard');
  });
});
