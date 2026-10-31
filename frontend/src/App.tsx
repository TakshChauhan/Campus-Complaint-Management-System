import { homePathForRole, AuthProvider, useAuth } from './context/AuthContext';
import { matchPath, Navigate, RouterProvider, useLocation } from './lib/router';
import { PublicOnly, RequireAuth, SessionLoading } from './routes/guards';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import ResendVerificationPage from './pages/ResendVerificationPage';
import StudentDashboard from './pages/StudentDashboard';
import RaiseComplaintPage from './pages/RaiseComplaintPage';
import MyComplaintsPage from './pages/MyComplaintsPage';
import ComplaintDetailPage from './pages/ComplaintDetailPage';
import ProfilePage from './pages/ProfilePage';
import StaffDashboard from './pages/StaffDashboard';
import AdminDashboard from './pages/AdminDashboard';
import CampusFeedPage from './pages/CampusFeedPage';
import NotFoundPage from './pages/NotFoundPage';

/**
 * Route table.
 *   /login, /register            public only
 *   /dashboard, /complaints/*    students
 *   /staff                       staff
 *   /admin                       admins
 *   /profile                     any signed-in user
 */
export function AppRoutes() {
  const { pathname } = useLocation();
  const { status, user } = useAuth();

  if (pathname === '/' || pathname === '') {
    if (status === 'restoring') return <SessionLoading />;
    return <Navigate to={user ? homePathForRole(user.role) : '/login'} />;
  }
  if (pathname === '/login') return <PublicOnly><LoginPage /></PublicOnly>;
  if (pathname === '/register') return <PublicOnly><RegisterPage /></PublicOnly>;
  // The emailed verification link must work even if a session is already present.
  if (pathname === '/verify-email') return <VerifyEmailPage />;
  if (pathname === '/resend-verification') return <ResendVerificationPage />;

  if (pathname === '/dashboard') return <RequireAuth roles={['student']}><StudentDashboard /></RequireAuth>;
  if (pathname === '/complaints/new') return <RequireAuth roles={['student']}><RaiseComplaintPage /></RequireAuth>;
  if (pathname === '/complaints') return <RequireAuth roles={['student']}><MyComplaintsPage /></RequireAuth>;
  const detail = matchPath('/complaints/:id', pathname);
  if (detail && /^\d+$/.test(detail.id)) {
    return <RequireAuth roles={['student']}><ComplaintDetailPage id={Number(detail.id)} /></RequireAuth>;
  }
  if (pathname === '/feed') return <RequireAuth><CampusFeedPage /></RequireAuth>;
  if (pathname === '/profile') return <RequireAuth><ProfilePage /></RequireAuth>;
  if (pathname === '/staff') return <RequireAuth roles={['staff']}><StaffDashboard /></RequireAuth>;
  if (pathname === '/admin') return <RequireAuth roles={['admin']}><AdminDashboard /></RequireAuth>;

  return <NotFoundPage />;
}

export default function App() {
  return (
    <RouterProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </RouterProvider>
  );
}
