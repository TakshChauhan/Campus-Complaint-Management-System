/**
 * Tiny fetch mock for integration tests: register handlers by "METHOD /path".
 * Paths are matched without the origin and without the query string; the
 * handler receives the parsed URL and JSON body.
 */
import { vi } from 'vitest';
import type { UserSafeResponse } from '../types';

export interface MockRequest {
  method: string;
  url: URL;
  body: unknown;
  headers: Headers;
}

type Handler = (req: MockRequest) => { status?: number; body?: unknown; headers?: Record<string, string> };

export function mockApi(handlers: Record<string, Handler>) {
  const calls: MockRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url);
    const method = (init?.method ?? 'GET').toUpperCase();
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    const req: MockRequest = { method, url, body, headers: new Headers(init?.headers) };
    calls.push(req);
    const key = `${method} ${url.pathname}`;
    const handler = handlers[key];
    if (!handler) {
      return new Response(JSON.stringify({ detail: `No mock for ${key}` }), {
        status: 599,
        headers: { 'content-type': 'application/json' },
      });
    }
    const { status = 200, body: resBody = null, headers = {} } = handler(req);
    return new Response(resBody === null ? null : JSON.stringify(resBody), {
      status,
      headers: { 'content-type': 'application/json', ...headers },
    });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, fetchMock, callsTo: (key: string) => calls.filter((c) => `${c.method} ${c.url.pathname}` === key) };
}

export function makeUser(overrides: Partial<UserSafeResponse> = {}): UserSafeResponse {
  return {
    id: 1,
    name: 'Aarav Patel',
    email: '202401001@dau.ac.in',
    role: 'student',
    is_active: true,
    email_verified: false,
    email_verified_at: null,
    department_id: null,
    created_at: '2026-10-01T10:00:00Z',
    ...overrides,
  };
}

/** Unsigned JWT-shaped token with the given exp (seconds). Only the client-side expiry check reads it. */
export function makeToken(expSecondsFromNow = 3600): string {
  const enc = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  const exp = Math.floor(Date.now() / 1000) + expSecondsFromNow;
  return `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc({ sub: '1', exp, iat: exp - 3600 })}.signature`;
}

export const DEPARTMENTS = [
  { id: 1, name: 'Hostel', description: 'Halls of residence maintenance', is_active: true },
  { id: 2, name: 'IT Services', description: 'Campus Wi-Fi and labs', is_active: true },
  { id: 3, name: 'Library', description: 'Resource Centre', is_active: true },
];
