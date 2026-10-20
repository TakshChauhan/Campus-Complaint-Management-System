import React from 'react';
import { homePathForRole, useAuth } from '../context/AuthContext';
import { Navigate, useLocation } from '../lib/router';
import { postLoginPath } from '../lib/access';
import { UserRole } from '../types';
import { AppShell } from '../layouts/AppShell';
import { ButtonLink, EmptyState, Spinner } from '../components/ui';

/** Full-screen placeholder while a stored session is being verified (prevents protected-content flashes). */
export function SessionLoading() {
  return (
    <div className="session-loading" role="status" aria-live="polite">
      <Spinner size={28} />
      <span>Checking your session…</span>
    </div>
  );
}

/**
 * Renders children only for an authenticated user whose role is allowed.
 * - Anonymous users go to /login with the requested path remembered.
 * - Wrong-role users see an explanation (the API enforces the same rule server-side).
 */
export function RequireAuth({ roles, children }: { roles?: UserRole[]; children: React.ReactNode }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === 'restoring') return <SessionLoading />;
  if (status !== 'authenticated' || !user) {
    const from = `${location.pathname}${location.search}`;
    return <Navigate to="/login" state={{ from }} />;
  }
  if (roles && !roles.includes(user.role)) {
    return (
      <AppShell>
        <EmptyState
          icon="shield"
          title="This page isn't available for your account"
          action={<ButtonLink to={homePathForRole(user.role)}>Go to your overview</ButtonLink>}
        >
          Your role doesn't include access to this page. If you think that's wrong, contact the CCMS administrator.
        </EmptyState>
      </AppShell>
    );
  }
  return <AppShell>{children}</AppShell>;
}

/** Sign-in / registration pages: an already signed-in user is sent to their overview. */
export function PublicOnly({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth();
  const location = useLocation();
  if (status === 'restoring') return <SessionLoading />;
  if (status === 'authenticated' && user) {
    const from = (location.state as { from?: unknown } | null)?.from;
    return <Navigate to={postLoginPath(from, user.role, homePathForRole(user.role))} />;
  }
  return <>{children}</>;
}
