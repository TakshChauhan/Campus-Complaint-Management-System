/**
 * Centralised, typed HTTP client for the CCMS FastAPI backend.
 *
 * VITE_API_BASE_URL is the backend ORIGIN (e.g. http://localhost:8000). A value
 * that already ends in /api/v1 is accepted and normalised, so the prefix is never
 * duplicated (".../api/v1/api/v1/...").
 */
import { ApiValidationErrorItem } from '../types';

export const API_PREFIX = '/api/v1';

export function normalizeApiBase(raw: string | undefined | null): string {
  const fallback = 'http://localhost:8000';
  let base = (raw ?? '').trim();
  if (!base) return fallback;
  base = base.replace(/\/+$/, '');
  base = base.replace(/\/api\/v1$/i, '');
  return base || fallback;
}

export const API_BASE_URL = normalizeApiBase(import.meta.env.VITE_API_BASE_URL);

/** Build a full URL. `path` is either an /api/v1 resource ("/complaints") or a root path ("/health"). */
export function apiUrl(path: string, { versioned = true }: { versioned?: boolean } = {}): string {
  const clean = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${versioned ? API_PREFIX : ''}${clean}`;
}

// ---------------------------------------------------------------- token storage

const TOKEN_KEY = 'ccms_auth_token';

export function getStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Storage unavailable (private mode). The session then lasts until reload.
  }
}

export function removeStoredToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // ignore
  }
}

/** Fired when an authenticated request is rejected with 401 (expired or revoked session). */
export const UNAUTHORIZED_EVENT = 'ccms:unauthorized';

// ---------------------------------------------------------------- errors

export class ApiClientError extends Error {
  status: number;
  validationErrors?: ApiValidationErrorItem[];
  rawDetail?: unknown;

  constructor(status: number, message: string, validationErrors?: ApiValidationErrorItem[], rawDetail?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.validationErrors = validationErrors;
    this.rawDetail = rawDetail;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

/** Map a validation error's field path ("body -> title") to the form field name ("title"). */
export function fieldFromLoc(field: string): string {
  const parts = field.split('->').map((p) => p.trim());
  return parts[parts.length - 1] || field;
}

function messageFromBody(status: number, body: unknown): { message: string; validationErrors?: ApiValidationErrorItem[] } {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return { message: detail };
    if (Array.isArray(detail)) {
      const validationErrors: ApiValidationErrorItem[] = detail.map((item: Record<string, unknown>) => ({
        field:
          typeof item.field === 'string'
            ? item.field
            : Array.isArray(item.loc)
              ? (item.loc as unknown[]).join(' -> ')
              : 'field',
        message: String(item.message ?? item.msg ?? 'Invalid value').replace(/^Value error, /, ''),
        type: typeof item.type === 'string' ? item.type : undefined,
      }));
      const message = validationErrors.map((v) => v.message).join(' ');
      return { message: message || 'Some fields are invalid.', validationErrors };
    }
  }
  if (status >= 500) return { message: 'The CCMS server ran into a problem. Try again in a moment.' };
  return { message: `Request failed (${status}).` };
}

// ---------------------------------------------------------------- request

export interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  /** Attach the stored bearer token (default true). */
  auth?: boolean;
  /** Prefix the path with /api/v1 (default true). */
  versioned?: boolean;
  /** Treat non-2xx statuses in this list as successful responses (e.g. 503 readiness). */
  acceptStatuses?: number[];
  signal?: AbortSignal;
}

export interface ApiResult<T> {
  data: T;
  headers: Headers;
  status: number;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const { method = 'GET', body, auth = true, versioned = true, acceptStatuses = [], signal } = options;
  const headers = new Headers({ Accept: 'application/json' });
  if (body !== undefined) headers.set('Content-Type', 'application/json');

  const token = auth ? getStoredToken() : null;
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(apiUrl(path, { versioned }), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiClientError(0, "Can't reach the CCMS server. Check your connection and try again.");
  }

  // Only an authenticated request can mean "your session ended". A 401 from the
  // login endpoint is just wrong credentials and must not trigger a logout notice.
  if (response.status === 401 && token) {
    removeStoredToken();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }

  const isJson = response.headers.get('content-type')?.includes('application/json');
  let data: unknown = null;
  try {
    data = isJson ? await response.json() : await response.text();
  } catch {
    data = null;
  }

  if (!response.ok && !acceptStatuses.includes(response.status)) {
    const { message, validationErrors } = messageFromBody(response.status, data);
    throw new ApiClientError(response.status, message, validationErrors, data);
  }

  return { data: data as T, headers: response.headers, status: response.status };
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { data } = await apiRequest<T>(path, options);
  return data;
}

/** User-facing message for any thrown error. */
export function errorMessage(err: unknown, fallback = 'Something went wrong. Try again.'): string {
  if (err instanceof ApiClientError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
