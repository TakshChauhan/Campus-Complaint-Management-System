import React, { useState } from 'react';
import { forgotPasswordApi } from '../api/auth';
import { errorMessage } from '../api/client';
import { Alert, Button, TextField } from '../components/ui';
import { AuthLayout } from '../layouts/AuthLayout';
import { Link, useLocation } from '../lib/router';
import { EMAIL_PATTERN } from '../lib/config';
import { useDocumentTitle } from '../hooks/useMediaState';

interface ForgotPageState {
  registeredEmail?: string;
  flash?: string;
}

export default function ForgotPasswordPage() {
  useDocumentTitle('Forgot password');
  const { state } = useLocation();
  const initial = (state ?? {}) as ForgotPageState;
  const [email, setEmail] = useState(initial.registeredEmail ?? '');
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setSuccess(null);
    setError(null);

    const trimmed = email.trim();
    if (!trimmed || !EMAIL_PATTERN.test(trimmed)) {
      setError('Enter a valid university email address.');
      return;
    }

    setBusy(true);
    try {
      const result = await forgotPasswordApi(trimmed.toLowerCase());
      // Always a neutral 202 message from backend
      setSuccess(result.message);
    } catch (err) {
      setError(errorMessage(err, 'Unable to send password reset email. Please try again.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout centered>
      <h1 className="auth-title">Forgot password</h1>
      <p className="auth-lede">
        Enter your university email address. If an account exists, we will send you a link to reset your password.
      </p>

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {initial.flash ? <Alert tone="info">{initial.flash}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        {success ? <Alert tone="success">{success}</Alert> : null}

        <TextField
          label="University email"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="202401001@dau.ac.in"
          required
          disabled={busy}
        />

        <Button block type="submit" loading={busy} disabled={busy}>
          {busy ? 'Sending reset link…' : 'Send reset link'}
        </Button>
      </form>

      <p className="auth-switch">
        Remembered your password? <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
