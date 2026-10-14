import { apiFetch, setStoredToken, removeStoredToken } from './client';
import { TokenResponse, UserSafeResponse } from '../types';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface GoogleAuthStartResponse {
  authorization_url: string;
  state: string;
}

export async function loginApi(payload: LoginPayload): Promise<TokenResponse> {
  const data = await apiFetch<TokenResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (data?.access_token) {
    setStoredToken(data.access_token);
  }
  return data;
}

export async function registerApi(payload: RegisterPayload): Promise<UserSafeResponse> {
  return await apiFetch<UserSafeResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function startGoogleAuthApi(client_challenge: string): Promise<GoogleAuthStartResponse> {
  return await apiFetch<GoogleAuthStartResponse>('/api/v1/auth/google/start', {
    method: 'POST',
    body: JSON.stringify({ client_challenge }),
  });
}

export async function exchangeGoogleTicketApi(
  ticket: string,
  client_verifier: string
): Promise<TokenResponse> {
  const data = await apiFetch<TokenResponse>('/api/v1/auth/google/exchange', {
    method: 'POST',
    body: JSON.stringify({ ticket, client_verifier }),
  });
  if (data?.access_token) {
    setStoredToken(data.access_token);
  }
  return data;
}

export async function getCurrentUserApi(): Promise<UserSafeResponse> {
  return await apiFetch<UserSafeResponse>('/api/v1/users/me', {
    method: 'GET',
  });
}

export function logoutApi(): void {
  removeStoredToken();
}
