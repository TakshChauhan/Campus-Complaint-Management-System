import React, { useState } from 'react';
import { resendVerificationApi } from '../api/auth';
import { errorMessage } from '../api/client';
import { Alert, Button, TextField } from '../components/ui';
import { AuthLayout } from '../layouts/AuthLayout';
import { Link, useLocation } from '../lib/router';
import { EMAIL_PATTERN } from '../lib/config';
import { useDocumentTitle } from '../hooks/useMediaState';

interface ResendPageState { registeredEmail?: string; flash?: string; }

export default function ResendVerificationPage() {
  useDocumentTitle('Resend verification');
  const { state } = useLocation();
  const initial = (state ?? {}) as ResendPageState;
  const [email, setEmail] = useState(initial.registeredEmail ?? '');
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resend = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setSuccess(null);
    setError(null);
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError('Enter a valid university email address.');
      return;
    }
    setBusy(true);
    try {
      const result = await resendVerificationApi(email.trim().toLowerCase());
      setSuccess(result.message); // always neutral: never disclose if account exists
    } catch (err) {
      setError(errorMessage(err, 'Unable to send the verification email right now.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout>
      <h1 className="auth-title">Resend verification email</h1>
      <p className="auth-lede">Enter the email you used to create your CCMS account.</p>
      <form className="auth-form" onSubmit={resend} noValidate>
        {initial.flash ? <Alert tone="info">{initial.flash}</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        {success ? <Alert tone="success">{success}</Alert> : null}
        <TextField
          label="University email" type="email" name="email" autoComplete="email"
          value={email} onChange={(event) => setEmail(event.target.value)}
          placeholder="202401001@dau.ac.in" required disabled={busy}
        />
        <Button block type="submit" loading={busy} disabled={busy}>Send verification email</Button>
      </form>
      <p className="auth-switch"><Link to="/login">Back to sign in</Link></p>
    </AuthLayout>
  );
}
