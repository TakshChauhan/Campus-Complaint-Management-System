import React, { useEffect, useRef, useState } from 'react';
import { verifyEmailApi } from '../api/auth';
import { errorMessage } from '../api/client';
import { Alert, Button } from '../components/ui';
import { AuthLayout } from '../layouts/AuthLayout';
import { Link, useLocation, useNavigate } from '../lib/router';
import { useDocumentTitle } from '../hooks/useMediaState';

type VerifyState = 'verifying' | 'verified' | 'error';

/** The one-time email token is only sent to our own API, never used as a JWT. */
export default function VerifyEmailPage() {
  useDocumentTitle('Verify email');
  const { search } = useLocation();
  const navigate = useNavigate();
  const token = new URLSearchParams(search).get('token')?.trim() ?? '';
  const [state, setState] = useState<VerifyState>('verifying');
  const [message, setMessage] = useState('Verifying your university email…');
  const [email, setEmail] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return; // React Strict Mode replays effects in development
    attempted.current = true;
    if (!token) {
      setState('error');
      setMessage('This link does not contain a verification token. Request a new email.');
      return;
    }
    verifyEmailApi(token)
      .then(({ message: success, email: verifiedEmail }) => {
        setState('verified');
        setMessage(success);
        setEmail(verifiedEmail);
        // Remove the consumed token from the browser URL without navigation.
        window.history.replaceState(window.history.state, '', '/verify-email');
      })
      .catch((err) => {
        setState('error');
        setMessage(errorMessage(err, 'Unable to verify your email. Request a new link.'));
      });
  }, [token]);

  return (
    <AuthLayout>
      <h1 className="auth-title">Email verification</h1>
      <p className="auth-lede">Confirm your university email to activate your CCMS student account.</p>
      <div className="auth-form">
        {state === 'verifying' ? <Alert tone="info">{message}</Alert> : null}
        {state === 'verified' ? (
          <>
            <Alert tone="success">{message}{email ? ` (${email})` : ''}</Alert>
            <Button type="button" block onClick={() => navigate('/login', { replace: true, state: { registeredEmail: email ?? undefined } })}>
              Continue to sign in
            </Button>
          </>
        ) : null}
        {state === 'error' ? (
          <>
            <Alert tone="error">{message}</Alert>
            <Link to="/resend-verification">Request another verification email</Link>
          </>
        ) : null}
      </div>
      <p className="auth-switch"><Link to="/login">Back to sign in</Link></p>
    </AuthLayout>
  );
}
