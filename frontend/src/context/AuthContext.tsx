import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { UserRole, UserSafeResponse } from '../types';
import {
  exchangeGoogleLinkTicketApi,
  exchangeGoogleTicketApi,
  getCurrentUserApi,
  loginApi,
  LoginPayload,
  registerApi,
  RegisterPayload,
  startGoogleAuthApi,
  startGoogleLinkApi,
} from '../api/auth';
import {
  API_BASE_URL,
  ApiClientError,
  getStoredToken,
  removeStoredToken,
  setStoredToken,
  UNAUTHORIZED_EVENT,
} from '../api/client';
import { isTokenExpired, readTokenExpiry } from '../lib/jwt';
import { generatePkceChallenge, generatePkceVerifier } from '../utils/crypto';

export type AuthStatus = 'restoring' | 'authenticated' | 'anonymous';

/** Why the last session ended — shown once on the sign-in page. */
export type SessionNotice = 'expired' | 'signed_out' | null;

interface AuthContextValue {
  status: AuthStatus;
  user: UserSafeResponse | null;
  notice: SessionNotice;
  clearNotice: () => void;
  login: (payload: LoginPayload) => Promise<UserSafeResponse>;
  loginWithGoogle: () => Promise<UserSafeResponse>;
  linkGoogleAccount: () => Promise<UserSafeResponse>;
  /** Creates the account only. Does NOT sign the user in. */
  register: (payload: RegisterPayload) => Promise<UserSafeResponse>;
  logout: (reason?: SessionNotice) => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const GOOGLE_MESSAGE_SUCCESS = 'CCMS_GOOGLE_AUTH_SUCCESS';
export const GOOGLE_MESSAGE_ERROR = 'CCMS_GOOGLE_AUTH_ERROR';
export const GOOGLE_LINK_MESSAGE_SUCCESS = 'CCMS_GOOGLE_LINK_SUCCESS';
export const GOOGLE_LINK_MESSAGE_ERROR = 'CCMS_GOOGLE_LINK_ERROR';

/**
 * Accept a postMessage only if it comes from the popup we opened AND from the
 * backend callback origin (or this app's origin when the API is proxied).
 */
export function isTrustedGoogleMessage(
  event: Pick<MessageEvent, 'origin' | 'source' | 'data'>,
  popup: Window | null,
  apiOrigin: string,
  appOrigin: string,
): boolean {
  if (!popup || event.source !== popup) return false;
  if (event.origin !== apiOrigin && event.origin !== appOrigin) return false;
  const data = event.data as { type?: unknown } | null;
  if (!data || typeof data !== 'object') return false;
  return (
    data.type === GOOGLE_MESSAGE_SUCCESS ||
    data.type === GOOGLE_MESSAGE_ERROR ||
    data.type === GOOGLE_LINK_MESSAGE_SUCCESS ||
    data.type === GOOGLE_LINK_MESSAGE_ERROR
  );
}

/** Landing page for each role after sign-in. */
export function homePathForRole(role: UserRole): string {
  if (role === 'admin') return '/admin';
  if (role === 'staff') return '/staff';
  return '/dashboard';
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('restoring');
  const [user, setUser] = useState<UserSafeResponse | null>(null);
  const [notice, setNotice] = useState<SessionNotice>(null);
  const expiryTimer = useRef<number | null>(null);

  const clearExpiryTimer = () => {
    if (expiryTimer.current !== null) {
      window.clearTimeout(expiryTimer.current);
      expiryTimer.current = null;
    }
  };

  const endSession = useCallback((reason: SessionNotice) => {
    clearExpiryTimer();
    removeStoredToken();
    setUser(null);
    setStatus('anonymous');
    setNotice(reason);
  }, []);

  /** Schedule an automatic sign-out when the token's exp passes. */
  const scheduleExpiry = useCallback(
    (token: string) => {
      clearExpiryTimer();
      const expiry = readTokenExpiry(token);
      if (expiry === null) return;
      const delay = expiry - Date.now();
      // setTimeout overflows above ~24.8 days; tokens are far shorter, but be safe.
      if (delay <= 0) {
        endSession('expired');
      } else if (delay < 2_147_000_000) {
        expiryTimer.current = window.setTimeout(() => endSession('expired'), delay);
      }
    },
    [endSession],
  );

  const startSession = useCallback(
    (token: string, profile: UserSafeResponse) => {
      setStoredToken(token);
      scheduleExpiry(token);
      setUser(profile);
      setNotice(null);
      setStatus('authenticated');
    },
    [scheduleExpiry],
  );

  // Restore a stored session on load (survives browser refresh).
  useEffect(() => {
    let cancelled = false;
    const token = getStoredToken();
    if (!token || isTokenExpired(token)) {
      if (token) removeStoredToken();
      setStatus('anonymous');
      if (token) setNotice('expired');
      return;
    }
    getCurrentUserApi()
      .then((profile) => {
        if (cancelled) return;
        scheduleExpiry(token);
        setUser(profile);
        setStatus('authenticated');
      })
      .catch((err) => {
        if (cancelled) return;
        // Without a verified profile we cannot show protected pages. A 401/403
        // means the token is unusable, so discard it; a network failure keeps it
        // so the next reload can restore the session once the server is back.
        const rejected = err instanceof ApiClientError && (err.status === 401 || err.status === 403);
        if (rejected) removeStoredToken();
        setUser(null);
        setStatus('anonymous');
        if (err instanceof ApiClientError && err.status === 401) setNotice('expired');
      });
    return () => {
      cancelled = true;
    };
  }, [scheduleExpiry]);

  // Any authenticated request rejected with 401 ends the session.
  useEffect(() => {
    const onUnauthorized = () => endSession('expired');
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
      clearExpiryTimer();
    };
  }, [endSession]);

  const login = useCallback(
    async (payload: LoginPayload) => {
      const res = await loginApi(payload);
      startSession(res.access_token, res.user);
      return res.user;
    },
    [startSession],
  );

  const register = useCallback(async (payload: RegisterPayload) => {
    // Deliberately no login here. The registration response is a profile, not a
    // session; the student is sent to the sign-in page to authenticate.
    return registerApi(payload);
  }, []);

  const loginWithGoogle = useCallback(async () => {
    // Open the popup synchronously inside the click handler to avoid popup blockers.
    const width = 500;
    const height = 650;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    const popup = window.open(
      'about:blank',
      'ccms_google_signin',
      `width=${width},height=${height},left=${left},top=${top},status=no,menubar=no,toolbar=no`,
    );
    if (!popup) {
      throw new Error('Your browser blocked the Google sign-in window. Allow pop-ups for this site and try again.');
    }

    try {
      // PKCE-style proof kept only in memory for this attempt.
      const verifier = generatePkceVerifier();
      const challenge = await generatePkceChallenge(verifier);
      const { authorization_url } = await startGoogleAuthApi(challenge);
      popup.location.href = authorization_url;

      const apiOrigin = new URL(API_BASE_URL).origin;
      const ticket = await new Promise<string>((resolve, reject) => {
        let done = false;
        const cleanup = () => {
          if (done) return;
          done = true;
          window.removeEventListener('message', onMessage);
          window.clearInterval(pollTimer);
          window.clearTimeout(timeoutTimer);
          if (!popup.closed) {
            try {
              popup.close();
            } catch {
              // ignore
            }
          }
        };
        const onMessage = (event: MessageEvent) => {
          if (!isTrustedGoogleMessage(event, popup, apiOrigin, window.location.origin)) return;
          const data = event.data as { type: string; ticket?: unknown; error?: unknown };
          cleanup();
          if (data.type === GOOGLE_MESSAGE_SUCCESS && typeof data.ticket === 'string') {
            resolve(data.ticket);
          } else {
            reject(new Error(typeof data.error === 'string' && data.error ? data.error : 'Google sign-in failed.'));
          }
        };
        window.addEventListener('message', onMessage);
        const pollTimer = window.setInterval(() => {
          if (popup.closed) {
            cleanup();
            reject(new Error('Google sign-in was cancelled because the window was closed.'));
          }
        }, 500);
        const timeoutTimer = window.setTimeout(() => {
          cleanup();
          reject(new Error('Google sign-in timed out. Try again.'));
        }, 300_000);
      });

      // Google sign-in IS authentication, so it opens a session directly.
      const tokenRes = await exchangeGoogleTicketApi(ticket, verifier);
      startSession(tokenRes.access_token, tokenRes.user);
      return tokenRes.user;
    } catch (err) {
      if (!popup.closed) {
        try {
          popup.close();
        } catch {
          // ignore
        }
      }
      throw err;
    }
  }, [startSession]);

  const linkGoogleAccount = useCallback(async () => {
    // Open the popup synchronously inside the click handler to avoid popup blockers.
    const width = 500;
    const height = 650;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    const popup = window.open(
      'about:blank',
      'ccms_google_link',
      `width=${width},height=${height},left=${left},top=${top},status=no,menubar=no,toolbar=no`,
    );
    if (!popup) {
      throw new Error('Your browser blocked the Google sign-in window. Allow pop-ups for this site and try again.');
    }

    try {
      const verifier = generatePkceVerifier();
      const challenge = await generatePkceChallenge(verifier);
      const { authorization_url } = await startGoogleLinkApi(challenge);
      popup.location.href = authorization_url;

      const apiOrigin = new URL(API_BASE_URL).origin;
      const ticket = await new Promise<string>((resolve, reject) => {
        let done = false;
        const cleanup = () => {
          if (done) return;
          done = true;
          window.removeEventListener('message', onMessage);
          window.clearInterval(pollTimer);
          window.clearTimeout(timeoutTimer);
          if (!popup.closed) {
            try {
              popup.close();
            } catch {
              // ignore
            }
          }
        };
        const onMessage = (event: MessageEvent) => {
          if (!isTrustedGoogleMessage(event, popup, apiOrigin, window.location.origin)) return;
          const data = event.data as { type: string; ticket?: unknown; error?: unknown };
          cleanup();
          if (
            (data.type === GOOGLE_LINK_MESSAGE_SUCCESS || data.type === GOOGLE_MESSAGE_SUCCESS) &&
            typeof data.ticket === 'string'
          ) {
            resolve(data.ticket);
          } else {
            reject(
              new Error(
                typeof data.error === 'string' && data.error ? data.error : 'Google account linking failed.',
              ),
            );
          }
        };
        window.addEventListener('message', onMessage);
        const pollTimer = window.setInterval(() => {
          if (popup.closed) {
            cleanup();
            reject(new Error('Google account linking was cancelled because the window was closed.'));
          }
        }, 500);
        const timeoutTimer = window.setTimeout(() => {
          cleanup();
          reject(new Error('Google account linking timed out. Try again.'));
        }, 300_000);
      });

      const linkRes = await exchangeGoogleLinkTicketApi(ticket, verifier);
      setUser(linkRes.user);
      return linkRes.user;
    } catch (err) {
      if (!popup.closed) {
        try {
          popup.close();
        } catch {
          // ignore
        }
      }
      throw err;
    }
  }, []);

  const logout = useCallback((reason: SessionNotice = 'signed_out') => endSession(reason), [endSession]);

  const refreshProfile = useCallback(async () => {
    const profile = await getCurrentUserApi();
    setUser(profile);
  }, []);

  const clearNotice = useCallback(() => setNotice(null), []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      notice,
      clearNotice,
      login,
      loginWithGoogle,
      linkGoogleAccount,
      register,
      logout,
      refreshProfile,
    }),
    [status, user, notice, clearNotice, login, loginWithGoogle, linkGoogleAccount, register, logout, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
