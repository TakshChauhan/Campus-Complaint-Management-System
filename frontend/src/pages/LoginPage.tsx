import React, { useEffect, useRef, useState } from 'react';
import { AuthLayout } from '../layouts/AuthLayout';
import { homePathForRole, useAuth } from '../context/AuthContext';
import { Link, useLocation, useNavigate } from '../lib/router';
import { postLoginPath } from '../lib/access';
import { ApiClientError, errorMessage } from '../api/client';
import { Alert, Button, PasswordField, TextField } from '../components/ui';
import { GoogleSignInButton } from '../components/GoogleSignInButton';
import { EMAIL_PATTERN, GOOGLE_AUTH_ENABLED } from '../lib/config';
import { useDocumentTitle } from '../hooks/useMediaState';

interface LoginLocationState {
  from?: string;
  registeredEmail?: string;
  flash?: string;
}

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.status === 401) return 'Incorrect email or password.';
    if (err.status === 422) return 'Enter a valid email address and your password.';
    return err.message; // 403 inactive account, 429 rate limit, network, 5xx
  }
  return errorMessage(err, 'Sign-in failed. Try again.');
}

export default function LoginPage() {
  useDocumentTitle('Sign in');
  const { login, loginWithGoogle, notice, clearNotice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const state = (location.state ?? {}) as LoginLocationState;

  const [email, setEmail] = useState(state.registeredEmail ?? '');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'password' | 'google' | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  // After registration the email is prefilled, so put the cursor in the password field.
  useEffect(() => {
    if (state.registeredEmail) passwordRef.current?.focus();
    else emailRef.current?.focus();
    // run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const goHome = (role: Parameters<typeof homePathForRole>[0]) => {
    navigate(postLoginPath(state.from, role, homePathForRole(role)), { replace: true });
  };

  const validate = () => {
    const errors: typeof fieldErrors = {};
    if (!email.trim()) errors.email = 'Enter your university email.';
    else if (!EMAIL_PATTERN.test(email.trim())) errors.email = 'Enter a valid email address, like 202401001@dau.ac.in.';
    if (!password) errors.password = 'Enter your password.';
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setFormError(null);
    clearNotice();
    if (!validate()) return;
    setBusy('password');
    try {
      const user = await login({ email: email.trim(), password });
      goHome(user.role);
    } catch (err) {
      setFormError(loginErrorMessage(err));
      setBusy(null);
    }
  };

  const handleGoogle = async () => {
    if (busy) return;
    setFormError(null);
    clearNotice();
    setBusy('google');
    try {
      const user = await loginWithGoogle();
      goHome(user.role);
    } catch (err) {
      const msg = errorMessage(err, 'Google sign-in could not be completed.');
      if (
        msg.toLowerCase().includes('account already exists') ||
        msg.toLowerCase().includes('connect google') ||
        msg.toLowerCase().includes('sign in using your password') ||
        msg.toLowerCase().includes('sign in with your email and password')
      ) {
        setFormError(
          'An account already exists with this email. Sign in using your password, then connect Google from your account settings.'
        );
      } else {
        setFormError(msg);
      }
      setBusy(null);
    }
  };

  return (
    <AuthLayout centered>
      <h1 className="auth-title">Sign in</h1>
      <p className="auth-lede">Report campus issues and follow up on the complaints you have raised.</p>

      <form className="auth-form" onSubmit={handleSubmit} noValidate aria-describedby={formError ? 'login-error' : undefined}>
        {state.flash ? <Alert tone="success">{state.flash}</Alert> : null}
        {notice === 'expired' && !state.flash ? (
          <Alert tone="info">Your session has expired. Sign in again to continue.</Alert>
        ) : null}
        {formError ? (
          <div id="login-error">
            <Alert tone="error">{formError}</Alert>
          </div>
        ) : null}

        <TextField
          ref={emailRef}
          label="University email"
          type="email"
          name="email"
          autoComplete="username"
          inputMode="email"
          placeholder="202401001@dau.ac.in"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          required
          disabled={busy !== null}
        />

        <PasswordField
          ref={passwordRef}
          label="Password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          error={fieldErrors.password}
          required
          disabled={busy !== null}
        />

        <Button type="submit" block loading={busy === 'password'} disabled={busy !== null}>
          {busy === 'password' ? 'Signing in…' : 'Sign in'}
        </Button>

        {GOOGLE_AUTH_ENABLED ? (
          <>
            <div className="auth-divider">or</div>
            <GoogleSignInButton onClick={handleGoogle} busy={busy === 'google'} disabled={busy !== null} />
          </>
        ) : null}
      </form>

      <p className="auth-switch">
        New to CCMS? <Link to="/register">Create a student account</Link>
      </p>
      <p className="auth-switch">
        Awaiting email verification? <Link to="/resend-verification" state={{ registeredEmail: email.trim() }}>Resend verification email</Link>
      </p>
    </AuthLayout>
  );
}
