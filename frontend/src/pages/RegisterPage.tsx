import React, { useRef, useState } from 'react';
import { AuthLayout } from '../layouts/AuthLayout';
import { useAuth } from '../context/AuthContext';
import { Link, useNavigate } from '../lib/router';
import { ApiClientError, errorMessage, fieldFromLoc } from '../api/client';
import { Alert, Button, Icon, PasswordField, TextField } from '../components/ui';
import { ALLOWED_EMAIL_DOMAINS, EMAIL_PATTERN, isAllowedEmailDomain, LIMITS } from '../lib/config';
import { useDocumentTitle } from '../hooks/useMediaState';

type FieldName = 'name' | 'email' | 'password' | 'confirm';
type Errors = Partial<Record<FieldName, string>>;

export const REGISTRATION_SUCCESS_MESSAGE = 'Account created! Check your inbox for the verification link. After verifying your email, you can sign in.';

const byteLength = (s: string) => new TextEncoder().encode(s).length;
const domainList = ALLOWED_EMAIL_DOMAINS.map((d) => `@${d}`).join(' or ');

function validate(values: Record<FieldName, string>): Errors {
  const errors: Errors = {};
  const name = values.name.trim();
  if (name.length < LIMITS.nameMin) errors.name = 'Enter your full name (at least 2 characters).';
  else if (name.length > LIMITS.nameMax) errors.name = 'Name can be at most 100 characters.';

  const email = values.email.trim();
  if (!email) errors.email = 'Enter your university email.';
  else if (!EMAIL_PATTERN.test(email)) errors.email = 'Enter a valid email address.';
  else if (!isAllowedEmailDomain(email)) errors.email = `Use your university email ending in ${domainList}.`;

  if (values.password.length < LIMITS.passwordMin) errors.password = 'Use at least 8 characters.';
  else if (!values.password.trim()) errors.password = "Password can't be only spaces.";
  else if (byteLength(values.password) > LIMITS.passwordMaxBytes) errors.password = 'Password is too long (72 bytes maximum).';

  if (!values.confirm) errors.confirm = 'Re-enter your password.';
  else if (values.confirm !== values.password) errors.confirm = "Passwords don't match.";
  return errors;
}

export default function RegisterPage() {
  useDocumentTitle('Create account');
  const { register } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState<Record<FieldName, string>>({ name: '', email: '', password: '', confirm: '' });
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inFlight = useRef(false);

  const clientErrors = validate(values);
  const visibleError = (field: FieldName) =>
    serverErrors[field] ?? ((touched[field] || submitted) ? clientErrors[field] : undefined);

  const update = (field: FieldName) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setValues((v) => ({ ...v, [field]: e.target.value }));
    if (serverErrors[field]) setServerErrors((s) => ({ ...s, [field]: undefined }));
  };
  const blur = (field: FieldName) => () => setTouched((t) => ({ ...t, [field]: true }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (inFlight.current) return;
    setSubmitted(true);
    setFormError(null);
    if (Object.keys(clientErrors).length > 0) return;

    inFlight.current = true;
    setSubmitting(true);
    const email = values.email.trim().toLowerCase();
    try {
      await register({ name: values.name.trim(), email, password: values.password });
      // Registration does not sign the student in. Send them to sign in, with the email prefilled.
      navigate('/login', { replace: true, state: { registeredEmail: email, flash: REGISTRATION_SUCCESS_MESSAGE } });
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 502 && err.message.toLowerCase().includes('account created')) {
        // Account was persisted, but mail delivery failed. Let them request a new
        // link instead of retrying /register and getting a duplicate-email error.
        navigate('/resend-verification', { replace: true, state: {
          registeredEmail: email,
          flash: 'Your account was created, but the verification email could not be delivered. Please request another link.',
        } });
      } else if (err instanceof ApiClientError && err.status === 409) {
        setServerErrors({ email: 'An account with this email already exists. Sign in instead.' });
      } else if (err instanceof ApiClientError && err.validationErrors?.length) {
        const mapped: Errors = {};
        for (const item of err.validationErrors) {
          const field = fieldFromLoc(item.field) as FieldName;
          if (field === 'name' || field === 'email' || field === 'password') mapped[field] = item.message;
        }
        if (Object.keys(mapped).length) setServerErrors(mapped);
        else setFormError(err.message);
      } else {
        setFormError(errorMessage(err, 'Registration failed. Try again.'));
      }
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  };

  const pw = values.password;
  const rules = [
    { met: pw.length >= LIMITS.passwordMin, text: 'At least 8 characters' },
    { met: pw.length > 0 && byteLength(pw) <= LIMITS.passwordMaxBytes && !!pw.trim(), text: 'No more than 72 characters, not only spaces' },
  ];

  return (
    <AuthLayout centered>
      <h1 className="auth-title">Create a student account</h1>
      <p className="auth-lede">Register with your university email. We'll email a verification link before you can sign in.</p>

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {formError ? <Alert tone="error">{formError}</Alert> : null}

        <TextField
          label="Full name"
          name="name"
          autoComplete="name"
          placeholder="Aarav Patel"
          value={values.name}
          onChange={update('name')}
          onBlur={blur('name')}
          error={visibleError('name')}
          maxLength={LIMITS.nameMax}
          required
          disabled={submitting}
        />
        <TextField
          label="University email"
          type="email"
          name="email"
          autoComplete="email"
          inputMode="email"
          placeholder="202401001@dau.ac.in"
          value={values.email}
          onChange={update('email')}
          onBlur={blur('email')}
          error={visibleError('email')}
          hint={`Must end in ${domainList}.`}
          required
          disabled={submitting}
        />
        <PasswordField
          label="Password"
          name="new-password"
          autoComplete="new-password"
          value={values.password}
          onChange={update('password')}
          onBlur={blur('password')}
          error={visibleError('password')}
          hint="A short phrase is easier to remember and harder to guess than a single word."
          required
          disabled={submitting}
        />
        <ul className="password-rules" aria-label="Password requirements">
          {rules.map((rule) => (
            <li key={rule.text} className={rule.met ? 'is-met' : undefined}>
              <Icon name={rule.met ? 'check' : 'info'} size={14} />
              <span>{rule.text}</span>
              <span className="visually-hidden">{rule.met ? '(met)' : '(not met yet)'}</span>
            </li>
          ))}
        </ul>
        <PasswordField
          label="Confirm password"
          name="confirm-password"
          autoComplete="new-password"
          value={values.confirm}
          onChange={update('confirm')}
          onBlur={blur('confirm')}
          error={visibleError('confirm')}
          required
          disabled={submitting}
        />

        <Button type="submit" block loading={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>

      <p className="auth-switch">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </AuthLayout>
  );
}
