import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getDepartmentsApi } from '../api/departments';
import { Alert, Button, DetailList, PageHeader, Panel } from '../components/ui';
import { formatDate, ROLE_LABELS } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';
import { GOOGLE_AUTH_ENABLED } from '../lib/config';
import { errorMessage } from '../api/client';

export default function ProfilePage() {
  useDocumentTitle('Profile');
  const { user, linkGoogleAccount } = useAuth();
  const [departmentName, setDepartmentName] = useState<string | null>(null);
  const [linkingBusy, setLinkingBusy] = useState(false);
  const [linkingSuccess, setLinkingSuccess] = useState<string | null>(null);
  const [linkingError, setLinkingError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.department_id) return;
    const controller = new AbortController();
    getDepartmentsApi(controller.signal)
      .then((list) => setDepartmentName(list.find((d) => d.id === user.department_id)?.name ?? null))
      .catch(() => setDepartmentName(null));
    return () => controller.abort();
  }, [user?.department_id]);

  if (!user) return null;

  const verification = user.email_verified
    ? `Verified${user.email_verified_at ? ` on ${formatDate(user.email_verified_at)}` : ''}`
    : 'Not verified. Please verify your email via the link sent to your inbox.';

  const handleConnectGoogle = async () => {
    if (linkingBusy) return;
    setLinkingSuccess(null);
    setLinkingError(null);
    setLinkingBusy(true);
    try {
      await linkGoogleAccount();
      setLinkingSuccess('Google account connected successfully. You can now sign in using either Google or your password.');
    } catch (err) {
      setLinkingError(errorMessage(err, 'Failed to connect Google account. Try again.'));
    } finally {
      setLinkingBusy(false);
    }
  };

  return (
    <div>
      <PageHeader title="Profile" description="Your CCMS account details and authentication settings." />

      {linkingSuccess ? (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <Alert tone="success">{linkingSuccess}</Alert>
        </div>
      ) : null}

      {linkingError ? (
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <Alert tone="error">{linkingError}</Alert>
        </div>
      ) : null}

      <Panel title="Profile Details">
        <DetailList
          items={[
            { label: 'Name', value: user.name },
            { label: 'University email', value: user.email },
            { label: 'Email verification', value: verification },
            { label: 'Role', value: ROLE_LABELS[user.role] },
            ...(user.department_id
              ? [{ label: 'Department', value: departmentName ?? `Department #${user.department_id}` }]
              : []),
            { label: 'Account created', value: formatDate(user.created_at) },
          ]}
        />
      </Panel>

      {GOOGLE_AUTH_ENABLED ? (
        <Panel
          title="Connected Accounts"
          className="account-linking-card"
        >
          <div className="account-linking-row">
            <div className="account-linking-info">
              <div className="account-linking-icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z" />
                  <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.24v3.15C3.26 21.36 7.33 24 12 24z" />
                  <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.24C.45 8.15 0 9.92 0 12s.45 3.85 1.24 5.42l4.04-3.15z" />
                  <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.24 6.58l4.04 3.15c.95-2.83 3.6-4.98 6.72-4.98z" />
                </svg>
              </div>
              <div className="account-linking-details">
                <span className="account-linking-title">Google Account</span>
                <span className="account-linking-desc">
                  {user.google_linked
                    ? `Connected (${user.email}). You can sign in using either Google or your password.`
                    : 'Connect your verified university Google account to sign in with either your password or Google.'}
                </span>
              </div>
            </div>

            <div>
              {user.google_linked ? (
                <span className="account-linking-status account-linking-status--connected">
                  <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', backgroundColor: '#10b981' }} />
                  Connected
                </span>
              ) : (
                <Button
                  onClick={handleConnectGoogle}
                  loading={linkingBusy}
                  disabled={linkingBusy}
                  variant="secondary"
                  size="sm"
                >
                  {linkingBusy ? 'Connecting…' : 'Connect Google Account'}
                </Button>
              )}
            </div>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
