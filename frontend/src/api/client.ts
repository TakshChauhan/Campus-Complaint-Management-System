import { ApiValidationErrorItem } from '../types';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000';

const TOKEN_KEY = 'ccms_auth_token';

export class ApiClientError extends Error {
  status: number;
  validationErrors?: ApiValidationErrorItem[];
  rawDetail?: any;

  constructor(status: number, message: string, validationErrors?: ApiValidationErrorItem[], rawDetail?: any) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.validationErrors = validationErrors;
    this.rawDetail = rawDetail;
  }
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export interface RequestOptions extends RequestInit {
  requiresAuth?: boolean;
}

export async function apiFetch<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const token = getStoredToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers,
    });
  } catch (err: any) {
    throw new ApiClientError(
      0,
      `Network connection failed. Could not reach backend at ${API_BASE_URL}. Ensure server is running.`
    );
  }

  // Handle Unauthorized (401)
  if (response.status === 401) {
    removeStoredToken();
    window.dispatchEvent(new Event('auth:unauthorized'));
  }

  // Parse response body
  const isJson = response.headers.get('content-type')?.includes('application/json');
  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    let errorMessage = `Server error (${response.status})`;
    let validationErrors: ApiValidationErrorItem[] | undefined;

    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') {
        errorMessage = data.detail;
      } else if (Array.isArray(data.detail)) {
        // FastAPI validation errors
        validationErrors = data.detail.map((item: any) => ({
          field: typeof item.field === 'string' ? item.field : (item.loc?.join(' -> ') || 'field'),
          message: item.message || item.msg || 'Invalid value',
          type: item.type,
        }));
        if (validationErrors && validationErrors.length > 0) {
          errorMessage = validationErrors.map((v) => `${v.field}: ${v.message}`).join(', ');
        }
      }
    }

    throw new ApiClientError(response.status, errorMessage, validationErrors, data);
  }

  return data as T;
}
