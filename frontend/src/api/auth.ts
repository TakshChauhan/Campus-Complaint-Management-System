import { apiFetch } from './client';
import { GoogleLinkExchangeResponse, GoogleLinkStatusResponse, TokenResponse, UserSafeResponse } from '../types';

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

/** POST /auth/login — returns a token; the caller (AuthContext) decides whether to store it. */
export function loginApi(payload: LoginPayload): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/auth/login', { method: 'POST', body: payload, auth: false });
}

/**
 * POST /auth/register — creates a student account and returns its public profile.
 * Registration never creates a browser session: the student signs in afterwards.
 */
export function registerApi(payload: RegisterPayload): Promise<UserSafeResponse> {
  return apiFetch<UserSafeResponse>('/auth/register', { method: 'POST', body: payload, auth: false });
}

export function startGoogleAuthApi(client_challenge: string): Promise<GoogleAuthStartResponse> {
  return apiFetch<GoogleAuthStartResponse>('/auth/google/start', {
    method: 'POST',
    body: { client_challenge },
    auth: false,
  });
}

export function exchangeGoogleTicketApi(ticket: string, client_verifier: string): Promise<TokenResponse> {
  return apiFetch<TokenResponse>('/auth/google/exchange', {
    method: 'POST',
    body: { ticket, client_verifier },
    auth: false,
  });
}

export function startGoogleLinkApi(client_challenge: string): Promise<GoogleAuthStartResponse> {
  return apiFetch<GoogleAuthStartResponse>('/auth/google/link/start', {
    method: 'POST',
    body: { client_challenge },
    auth: true,
  });
}

export function exchangeGoogleLinkTicketApi(ticket: string, client_verifier: string): Promise<GoogleLinkExchangeResponse> {
  return apiFetch<GoogleLinkExchangeResponse>('/auth/google/link/exchange', {
    method: 'POST',
    body: { ticket, client_verifier },
    auth: true,
  });
}

export function getGoogleStatusApi(): Promise<GoogleLinkStatusResponse> {
  return apiFetch<GoogleLinkStatusResponse>('/auth/google/status', {
    method: 'GET',
    auth: true,
  });
}

export function getCurrentUserApi(): Promise<UserSafeResponse> {
  return apiFetch<UserSafeResponse>('/users/me');
}

export interface VerifyEmailResponse {
  message: string;
  email: string | null;
}

export interface ResendVerificationResponse {
  message: string;
}

/** Verifies an emailed, single-use token; does NOT create an authenticated session. */
export function verifyEmailApi(token: string): Promise<VerifyEmailResponse> {
  return apiFetch<VerifyEmailResponse>('/auth/verify-email', {
    method: 'POST', body: { token }, auth: false,
  });
}

/** Neutral response, including for an email address with no account. */
export function resendVerificationApi(email: string): Promise<ResendVerificationResponse> {
  return apiFetch<ResendVerificationResponse>('/auth/resend-verification', {
    method: 'POST', body: { email }, auth: false,
  });
}
