import { UserRole } from '../types';
import { isSafeInternalPath } from './router';

/** Which signed-in roles may open a given app path (mirrors the route table in App.tsx). */
export function rolesForPath(pathname: string): UserRole[] | 'any' | null {
  if (pathname === '/profile') return 'any';
  if (pathname === '/dashboard' || pathname === '/complaints' || pathname === '/complaints/new' || /^\/complaints\/\d+$/.test(pathname)) {
    return ['student'];
  }
  if (pathname === '/staff') return ['staff'];
  if (pathname === '/admin') return ['admin'];
  return null;
}

/**
 * Where to go after sign-in: the page the user originally asked for, but only if
 * it is an internal path their role may open; otherwise their role's overview.
 */
export function postLoginPath(from: unknown, role: UserRole, home: string): string {
  if (!isSafeInternalPath(from)) return home;
  const pathname = from.split(/[?#]/)[0];
  const allowed = rolesForPath(pathname);
  if (allowed === 'any' || (Array.isArray(allowed) && allowed.includes(role))) return from;
  return home;
}
