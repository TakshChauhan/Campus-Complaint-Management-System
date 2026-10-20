import { homePathForRole, useAuth } from '../context/AuthContext';
import { ButtonLink, EmptyState } from '../components/ui';
import { useDocumentTitle } from '../hooks/useMediaState';

export default function NotFoundPage() {
  useDocumentTitle('Page not found');
  const { user } = useAuth();
  return (
    <main className="standalone" id="main">
      <EmptyState
        icon="search"
        title="Page not found"
        action={<ButtonLink to={user ? homePathForRole(user.role) : '/login'}>{user ? 'Go to your overview' : 'Go to sign in'}</ButtonLink>}
      >
        The address may be mistyped, or the page has moved.
      </EmptyState>
    </main>
  );
}
