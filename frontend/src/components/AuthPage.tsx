import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { ApiClientError } from '../api/client';
import './AuthPage.css';

export default function AuthPage() {
  const { login, loginWithGoogle, register } = useAuth();
  const [tab, setTab] = useState<'login' | 'register'>('login');

  // Login form state
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Register form state
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Feature flag for Google authentication integration
  const isGoogleAuthEnabled = import.meta.env.VITE_GOOGLE_AUTH_ENABLED !== 'false';

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      await login({ email: loginEmail.trim(), password: loginPassword });
    } catch (err: any) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Failed to sign in. Please check your credentials.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    setErrorMessage(null);
    setIsLoading(true);

    try {
      await loginWithGoogle();
    } catch (err: any) {
      const msg = err?.message || 'Google sign-in could not be completed.';
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsLoading(true);

    try {
      await register({
        name: regName.trim(),
        email: regEmail.trim(),
        password: regPassword,
      });
    } catch (err: any) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Registration failed. Please check form entries.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-card">
      <div className="auth-header">
        <h2>Campus Complaint Portal</h2>
        <p>Sign in with your university credentials to manage or submit campus complaints</p>
      </div>

      <div className="auth-tabs">
        <button
          type="button"
          className={`auth-tab-btn ${tab === 'login' ? 'active' : ''}`}
          onClick={() => {
            setTab('login');
            setErrorMessage(null);
          }}
        >
          Sign In
        </button>
        <button
          type="button"
          className={`auth-tab-btn ${tab === 'register' ? 'active' : ''}`}
          onClick={() => {
            setTab('register');
            setErrorMessage(null);
          }}
        >
          Register Student
        </button>
      </div>

      {errorMessage && (
        <div className="auth-error-banner" role="alert">
          {errorMessage}
        </div>
      )}

      {/* Google Sign-In Option */}
      {isGoogleAuthEnabled && (
        <div style={{ marginBottom: '16px' }}>
          <button
            type="button"
            className="google-login-btn"
            onClick={handleGoogleLogin}
            disabled={isLoading}
          >
            <svg className="google-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.24v3.15C3.26 21.36 7.33 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.24C.45 8.15 0 9.92 0 12s.45 3.85 1.24 5.42l4.04-3.15z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.24 6.58l4.04 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
              />
            </svg>
            <span>Sign in with Google</span>
          </button>

          <div className="auth-divider">
            <span>or sign in with password</span>
          </div>
        </div>
      )}

      {tab === 'login' ? (
        <form onSubmit={handleLoginSubmit} className="auth-form" noValidate>
          <div className="auth-field">
            <label htmlFor="login-email">Email Address</label>
            <input
              id="login-email"
              type="email"
              className="auth-input"
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
              placeholder="e.g. student@campus.edu"
              required
              disabled={isLoading}
            />
          </div>

          <div className="auth-field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              className="auth-input"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              placeholder="Enter your password"
              required
              disabled={isLoading}
            />
          </div>

          <button type="submit" className="btn-primary auth-submit-btn" disabled={isLoading}>
            {isLoading ? 'Signing In...' : 'Sign In'}
          </button>
        </form>
      ) : (
        <form onSubmit={handleRegisterSubmit} className="auth-form" noValidate>
          <div className="auth-field">
            <label htmlFor="reg-name">Full Name</label>
            <input
              id="reg-name"
              type="text"
              className="auth-input"
              value={regName}
              onChange={(e) => setRegName(e.target.value)}
              placeholder="e.g. Aarav Patel"
              minLength={2}
              maxLength={100}
              required
              disabled={isLoading}
            />
            <span className="auth-hint">Minimum 2 characters</span>
          </div>

          <div className="auth-field">
            <label htmlFor="reg-email">Student Email Address</label>
            <input
              id="reg-email"
              type="email"
              className="auth-input"
              value={regEmail}
              onChange={(e) => setRegEmail(e.target.value)}
              placeholder="e.g. 202401223@dau.ac.in or 202101001@daiict.ac.in"
              required
              disabled={isLoading}
            />
            <span className="auth-hint">Must be an official university email (e.g. ending in @dau.ac.in or @daiict.ac.in)</span>
          </div>

          <div className="auth-field">
            <label htmlFor="reg-password">Password</label>
            <input
              id="reg-password"
              type="password"
              className="auth-input"
              value={regPassword}
              onChange={(e) => setRegPassword(e.target.value)}
              placeholder="Minimum 8 characters"
              minLength={8}
              maxLength={72}
              required
              disabled={isLoading}
            />
            <span className="auth-hint">8–72 characters</span>
          </div>

          <button type="submit" className="btn-primary auth-submit-btn" disabled={isLoading}>
            {isLoading ? 'Creating Account...' : 'Register Student Account'}
          </button>
        </form>
      )}
    </div>
  );
}
