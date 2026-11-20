import React, { useState } from 'react';
import { resetPasswordApi } from '../api/auth';
import { ApiClientError, errorMessage } from '../api/client';
import { Alert, Button, Icon, PasswordField } from '../components/ui';
import { AuthLayout } from '../layouts/AuthLayout';
import { Link, useLocation, useNavigate } from '../lib/router';
import { LIMITS } from '../lib/config';
import { useDocumentTitle } from '../hooks/useMediaState';

const byteLength = (s: string) => new TextEncoder().encode(s).length;

export default function ResetPasswordPage() {
  useDocumentTitle('Reset password');
  const navigate = useNavigate();
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const token = searchParams.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirmPassword?: string }>({});
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rules = [
    { met: password.length >= LIMITS.passwordMin, text: 'At least 8 characters' },
    { met: password.length > 0 && byteLength(password) <= LIMITS.passwordMaxBytes && !!password.trim(), text: 'No more than 72 characters, not only spaces' },
  ];

  const validate = (): boolean => {
    const errors: typeof fieldErrors = {};
    if (!password) {
      errors.password = 'Enter a new password.';
    } else if (password.length < LIMITS.passwordMin) {
      errors.password = `Password must be at least ${LIMITS.passwordMin} characters.`;
    } else if (byteLength(password) > LIMITS.passwordMaxBytes) {
      errors.password = 'Password is too long (maximum 72 bytes).';
    } else if (!password.trim()) {
      errors.password = 'Password cannot be entirely whitespace.';
    }

    if (!confirmPassword) {
      errors.confirmPassword = 'Confirm your new password.';
    } else if (password && confirmPassword !== password) {
      errors.confirmPassword = 'Passwords do not match.';
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setSuccess(null);

    if (!token.trim()) {
      setError('Invalid or missing password reset link. Please request a new link.');
      return;
    }

    if (!validate()) return;

    setBusy(true);
    try {
      const result = await resetPasswordApi({ token: token.trim(), password });
      setSuccess(result.message || 'Password has been successfully reset.');
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 400) {
        setError('This reset link is invalid, expired, or has already been used. Please request a new one.');
      } else {
        setError(errorMessage(err, 'Unable to reset password. Please try again.'));
      }
    } finally {
      setBusy(false);
    }
  };

  if (!token.trim()) {
    return (
      <AuthLayout centered>
        <h1 className="auth-title">Invalid reset link</h1>
        <p className="auth-lede">
          No reset token was found in the link. Please request a new password reset link.
        </p>
        <div style={{ marginTop: 'var(--space-6)' }}>
          <Button block onClick={() => navigate('/forgot-password')}>
            Request new reset link
          </Button>
        </div>
        <p className="auth-switch">
          <Link to="/login">Back to sign in</Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout centered>
      <h1 className="auth-title">Reset your password</h1>
      <p className="auth-lede">Enter and confirm your new account password below.</p>

      {success ? (
        <div style={{ marginTop: 'var(--space-6)' }}>
          <Alert tone="success">{success}</Alert>
          <div style={{ marginTop: 'var(--space-6)' }}>
            <Button block onClick={() => navigate('/login')}>
              Sign in with new password
            </Button>
          </div>
        </div>
      ) : (
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {error ? <Alert tone="error">{error}</Alert> : null}

          <PasswordField
            label="New password"
            name="new-password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={fieldErrors.password}
            required
            disabled={busy}
          />

          <ul className="password-rules" aria-label="Password requirements">
            {rules.map((rule) => (
              <li key={rule.text} className={rule.met ? 'is-met' : undefined}>
                <Icon name={rule.met ? 'check' : 'info'} size={14} />
                <span>{rule.text}</span>
              </li>
            ))}
          </ul>

          <PasswordField
            label="Confirm new password"
            name="confirm-password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            error={fieldErrors.confirmPassword}
            required
            disabled={busy}
          />

          <Button block type="submit" loading={busy} disabled={busy}>
            {busy ? 'Resetting password…' : 'Set new password'}
          </Button>
        </form>
      )}

      <p className="auth-switch">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
