import React, { createContext, useContext, useEffect, useState } from 'react';
import { UserSafeResponse } from '../types';
import {
  getCurrentUserApi,
  loginApi,
  logoutApi,
  registerApi,
  startGoogleAuthApi,
  exchangeGoogleTicketApi,
  LoginPayload,
  RegisterPayload,
} from '../api/auth';
import { API_BASE_URL, getStoredToken, removeStoredToken } from '../api/client';
import { generatePkceChallenge, generatePkceVerifier } from '../utils/crypto';

interface AuthContextType {
  user: UserSafeResponse | null;
  token: string | null;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<UserSafeResponse>;
  loginWithGoogle: () => Promise<UserSafeResponse>;
  register: (payload: RegisterPayload) => Promise<UserSafeResponse>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserSafeResponse | null>(null);
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Restore authenticated session on app mount
  useEffect(() => {
    async function restoreSession() {
      const storedToken = getStoredToken();
      if (!storedToken) {
        setIsLoading(false);
        return;
      }

      try {
        const profile = await getCurrentUserApi();
        setUser(profile);
        setToken(storedToken);
      } catch (err) {
        removeStoredToken();
        setUser(null);
        setToken(null);
      } finally {
        setIsLoading(false);
      }
    }

    restoreSession();

    // Listen for unauthorized 401 broadcast events from API client
    const handleUnauthorized = () => {
      setUser(null);
      setToken(null);
      removeStoredToken();
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, []);

  const login = async (payload: LoginPayload): Promise<UserSafeResponse> => {
    const res = await loginApi(payload);
    setUser(res.user);
    setToken(res.access_token);
    return res.user;
  };

  const loginWithGoogle = async (): Promise<UserSafeResponse> => {
    // 1. Synchronously open popup from user gesture to avoid popup blocker
    const width = 500;
    const height = 650;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    const popup = window.open(
      'about:blank',
      'ccms_google_signin',
      `width=${width},height=${height},left=${left},top=${top},status=no,menubar=no,toolbar=no`
    );

    if (!popup) {
      throw new Error('Popup blocked by browser. Please enable popups for this site to sign in with Google.');
    }

    try {
      // 2. Generate random PKCE verifier and challenge in memory
      const verifier = generatePkceVerifier();
      const challenge = await generatePkceChallenge(verifier);

      // 3. Initiate OAuth start endpoint on backend
      const { authorization_url } = await startGoogleAuthApi(challenge);
      popup.location.href = authorization_url;

      // 4. Await postMessage from callback popup with origin verification and timeout
      const ticket = await new Promise<string>((resolve, reject) => {
        let cleanupDone = false;

        const cleanup = () => {
          if (cleanupDone) return;
          cleanupDone = true;
          window.removeEventListener('message', handleMessage);
          clearInterval(pollTimer);
          clearTimeout(timeoutTimer);
          if (popup && !popup.closed) {
            try {
              popup.close();
            } catch {
              // ignore
            }
          }
        };

        const handleMessage = (event: MessageEvent) => {
          // Verify message origin matches API server origin or frontend origin
          const expectedApiOrigin = new URL(API_BASE_URL).origin;
          if (event.origin !== expectedApiOrigin && event.origin !== window.location.origin) {
            return;
          }

          if (event.source !== popup) {
            return;
          }

          const data = event.data;
          if (!data || typeof data !== 'object') {
            return;
          }

          if (data.type === 'CCMS_GOOGLE_AUTH_SUCCESS' && typeof data.ticket === 'string') {
            cleanup();
            resolve(data.ticket);
          } else if (data.type === 'CCMS_GOOGLE_AUTH_ERROR') {
            cleanup();
            const msg = data.error || 'Google authentication failed.';
            reject(new Error(msg));
          }
        };

        window.addEventListener('message', handleMessage);

        const pollTimer = setInterval(() => {
          if (popup.closed) {
            cleanup();
            reject(new Error('Sign-in cancelled. The Google sign-in window was closed.'));
          }
        }, 500);

        const timeoutTimer = setTimeout(() => {
          cleanup();
          reject(new Error('Google sign-in timed out. Please try again.'));
        }, 300000);
      });

      // 5. Exchange single-use handoff ticket with client verifier proof
      const tokenRes = await exchangeGoogleTicketApi(ticket, verifier);
      setUser(tokenRes.user);
      setToken(tokenRes.access_token);

      // Fetch fresh profile from /api/v1/users/me
      try {
        const freshProfile = await getCurrentUserApi();
        setUser(freshProfile);
        return freshProfile;
      } catch {
        return tokenRes.user;
      }
    } catch (err: any) {
      if (popup && !popup.closed) {
        try {
          popup.close();
        } catch {
          // ignore
        }
      }
      throw err;
    }
  };

  const register = async (payload: RegisterPayload): Promise<UserSafeResponse> => {
    const newUser = await registerApi(payload);
    // After registration, log user in to obtain token
    const res = await loginApi({ email: payload.email, password: payload.password });
    setUser(res.user);
    setToken(res.access_token);
    return res.user;
  };

  const logout = () => {
    logoutApi();
    setUser(null);
    setToken(null);
  };

  const refreshProfile = async () => {
    try {
      const profile = await getCurrentUserApi();
      setUser(profile);
    } catch {
      logout();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        login,
        loginWithGoogle,
        register,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
