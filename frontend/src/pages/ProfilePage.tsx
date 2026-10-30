import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getDepartmentsApi } from '../api/departments';
import { getMyResidenceApi, updateMyResidenceApi } from '../api/residence';
import { LocationPicker } from '../components/LocationPicker';
import { Alert, Button, DetailList, EmptyState, PageHeader, Panel, Skeleton, StatusBadge } from '../components/ui';
import { formatDate, ROLE_LABELS } from '../lib/format';
import { useDocumentTitle } from '../hooks/useMediaState';
import { GOOGLE_AUTH_ENABLED } from '../lib/config';
import { errorMessage } from '../api/client';
import { MyResidence } from '../types';

export default function ProfilePage() {
  useDocumentTitle('Profile');
  const { user, linkGoogleAccount } = useAuth();
  const [departmentName, setDepartmentName] = useState<string | null>(null);
  const [linkingBusy, setLinkingBusy] = useState(false);
  const [linkingSuccess, setLinkingSuccess] = useState<string | null>(null);
  const [linkingError, setLinkingError] = useState<string | null>(null);

  // Student residence state
  const [residence, setResidence] = useState<MyResidence | null>(null);
  const [residenceLoading, setResidenceLoading] = useState(user?.role === 'student');
  const [residenceError, setResidenceError] = useState<string | null>(null);
  const [isEditingResidence, setIsEditingResidence] = useState(false);
  const [selectedFloorId, setSelectedFloorId] = useState<number | null>(null);
  const [residenceSaving, setResidenceSaving] = useState(false);
  const [residenceSaveError, setResidenceSaveError] = useState<string | null>(null);
  const [residenceSaveSuccess, setResidenceSaveSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.department_id) return;
    const controller = new AbortController();
    getDepartmentsApi(controller.signal)
      .then((list) => setDepartmentName(list.find((d) => d.id === user.department_id)?.name ?? null))
      .catch(() => setDepartmentName(null));
    return () => controller.abort();
  }, [user?.department_id]);

  const loadResidence = useCallback((signal?: AbortSignal) => {
    if (user?.role !== 'student') return;
    setResidenceLoading(true);
    setResidenceError(null);
    getMyResidenceApi(signal)
      .then((res) => {
        setResidence(res);
        setResidenceLoading(false);
      })
      .catch((err) => {
        if (signal?.aborted) return;
        setResidenceError(errorMessage(err, "Couldn't load your residence information."));
        setResidenceLoading(false);
      });
  }, [user?.role]);

  useEffect(() => {
    const controller = new AbortController();
    loadResidence(controller.signal);
    return () => controller.abort();
  }, [loadResidence]);

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

  const handleSaveResidence = async () => {
    if (!selectedFloorId || residenceSaving) return;
    setResidenceSaving(true);
    setResidenceSaveError(null);
    setResidenceSaveSuccess(null);

    try {
      const updated = await updateMyResidenceApi(selectedFloorId);
      setResidence(updated);
      setIsEditingResidence(false);
      setResidenceSaveSuccess('Residence updated successfully. Verification status is now pending review.');
    } catch (err) {
      setResidenceSaveError(errorMessage(err, 'Failed to save residence. Please try again.'));
    } finally {
      setResidenceSaving(false);
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

      {/* Student Hostel Residence Section */}
      {user.role === 'student' ? (
        <Panel
          title="Hostel Residence"
          action={
            !isEditingResidence && residence && !residenceLoading ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setSelectedFloorId(residence.floor_id);
                  setResidenceSaveError(null);
                  setResidenceSaveSuccess(null);
                  setIsEditingResidence(true);
                }}
              >
                Change residence
              </Button>
            ) : null
          }
        >
          {residenceSaveSuccess ? (
            <div style={{ marginBottom: 'var(--space-4)' }}>
              <Alert tone="success">{residenceSaveSuccess}</Alert>
            </div>
          ) : null}

          {residenceLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }} aria-busy="true">
              <Skeleton width="40%" height={16} />
              <Skeleton width="80%" height={20} />
              <Skeleton width="60%" height={20} />
            </div>
          ) : residenceError ? (
            <Alert
              tone="error"
              title="Couldn't load residence details"
              action={
                <Button size="sm" variant="secondary" icon="refresh" onClick={() => loadResidence()}>
                  Retry
                </Button>
              }
            >
              {residenceError}
            </Alert>
          ) : isEditingResidence ? (
            <div className="residence-editor">
              <Alert tone="warning" title="Verification reset notice">
                Declaring or changing your residence will submit it for hostel staff verification.
                Your verification status will be set to pending for review.
              </Alert>

              <div style={{ marginTop: 'var(--space-4)', marginBottom: 'var(--space-4)' }}>
                <LocationPicker
                  value={selectedFloorId}
                  onChange={(fid) => {
                    setSelectedFloorId(fid);
                    setResidenceSaveError(null);
                  }}
                  required
                  error={residenceSaveError}
                  disabled={residenceSaving}
                />
              </div>

              <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
                <Button
                  onClick={handleSaveResidence}
                  loading={residenceSaving}
                  disabled={!selectedFloorId || residenceSaving}
                  size="sm"
                >
                  {residenceSaving ? 'Saving…' : 'Save residence'}
                </Button>
                {residence ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setIsEditingResidence(false);
                      setResidenceSaveError(null);
                    }}
                    disabled={residenceSaving}
                  >
                    Cancel
                  </Button>
                ) : null}
              </div>
            </div>
          ) : residence ? (
            <div className="residence-display">
              {residence.status === 'rejected' ? (
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <Alert tone="error" title="Residence verification rejected">
                    {residence.remark
                      ? `Staff remark: "${residence.remark}". Please update your declared residence.`
                      : 'Your declared hostel residence was rejected by hostel administration. Please update your residence.'}
                  </Alert>
                </div>
              ) : residence.status === 'pending' ? (
                <div style={{ marginBottom: 'var(--space-4)' }}>
                  <Alert tone="info" title="Verification pending">
                    Your declared hostel residence is under review by hostel administration.
                  </Alert>
                </div>
              ) : null}

              <DetailList
                items={[
                  { label: 'Hostel building', value: residence.hostel },
                  { label: 'Wing / Block', value: residence.wing },
                  { label: 'Floor', value: residence.floor },
                  {
                    label: 'Verification status',
                    value: <StatusBadge status={residence.status} />,
                  },
                ]}
              />
            </div>
          ) : (
            <EmptyState
              icon="building"
              title="No residence declared"
              action={
                <Button
                  size="sm"
                  onClick={() => {
                    setSelectedFloorId(null);
                    setResidenceSaveError(null);
                    setResidenceSaveSuccess(null);
                    setIsEditingResidence(true);
                  }}
                >
                  Declare residence
                </Button>
              }
            >
              You haven't declared your hostel residence yet. Declaring your hostel room allows hostel-specific
              service routing and access to verified resident feeds.
            </EmptyState>
          )}
        </Panel>
      ) : null}

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
