import React, { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from '../lib/router';
import { useAuth } from '../context/AuthContext';
import { Icon, IconName } from '../components/ui';
import { ROLE_LABELS } from '../lib/format';
import { UserRole } from '../types';
import './AppShell.css';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  /** Also highlight for these path prefixes. */
  match?: (path: string) => boolean;
}

const NAV_BY_ROLE: Record<UserRole, NavItem[]> = {
  student: [
    { to: '/dashboard', label: 'Dashboard', icon: 'dashboard' },
    { to: '/complaints/new', label: 'Raise complaint', icon: 'plus' },
    {
      to: '/complaints',
      label: 'My complaints',
      icon: 'list',
      match: (p) => p === '/complaints' || (/^\/complaints\/\d+$/.test(p)),
    },
    { to: '/profile', label: 'Profile', icon: 'user' },
  ],
  staff: [
    { to: '/staff', label: 'Staff overview', icon: 'dashboard' },
    { to: '/profile', label: 'Profile', icon: 'user' },
  ],
  admin: [
    { to: '/admin', label: 'System overview', icon: 'dashboard' },
    { to: '/profile', label: 'Profile', icon: 'user' },
  ],
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close the mobile drawer on navigation.
  useEffect(() => setDrawerOpen(false), [pathname]);

  // Escape closes the drawer; focus moves into it on open and back on close.
  useEffect(() => {
    if (!drawerOpen) return;
    const firstLink = drawerRef.current?.querySelector<HTMLElement>('a, button');
    firstLink?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    const menuButton = menuButtonRef.current;
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      menuButton?.focus();
    };
  }, [drawerOpen]);

  if (!user) return null;
  const items = NAV_BY_ROLE[user.role];

  const handleLogout = () => {
    logout('signed_out');
    navigate('/login', { replace: true });
  };

  const isActive = (item: NavItem) => (item.match ? item.match(pathname) : pathname === item.to);

  const nav = (
    <>
      <nav className="shell-nav" aria-label="Main">
        <ul>
          {items.map((item) => (
            <li key={item.to}>
              <Link
                to={item.to}
                className={['shell-nav__link', isActive(item) && 'is-active'].filter(Boolean).join(' ')}
                aria-current={isActive(item) ? 'page' : undefined}
              >
                <Icon name={item.icon} size={20} />
                <span>{item.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="shell-user">
        <div className="shell-user__info">
          <span className="shell-user__name">{user.name}</span>
          <span className="shell-user__role">{ROLE_LABELS[user.role]}</span>
        </div>
        <button type="button" className="shell-nav__link shell-nav__logout" onClick={handleLogout}>
          <Icon name="logout" size={20} />
          <span>Sign out</span>
        </button>
      </div>
    </>
  );

  return (
    <div className="shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <aside className="shell-sidebar">
        <Link to={items[0].to} className="shell-brand" aria-label="CCMS home">
          <img src="/dau-logo-light.png" alt="" width={84} height={44} />
          <span className="shell-brand__name">Campus Complaints</span>
        </Link>
        {nav}
      </aside>

      <header className="shell-topbar">
        <Link to={items[0].to} className="shell-brand shell-brand--compact" aria-label="CCMS home">
          <img src="/dau-logo-light.png" alt="" width={64} height={34} />
          <span className="shell-brand__name">Campus Complaints</span>
        </Link>
        <button
          ref={menuButtonRef}
          type="button"
          className="shell-menu-btn"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open menu"
          aria-expanded={drawerOpen}
          aria-controls="shell-drawer"
        >
          <Icon name="menu" size={22} />
        </button>
      </header>

      {drawerOpen ? (
        <div className="shell-drawer-backdrop" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
      ) : null}
      <div
        id="shell-drawer"
        ref={drawerRef}
        className={['shell-drawer', drawerOpen && 'is-open'].filter(Boolean).join(' ')}
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        hidden={!drawerOpen}
      >
        <div className="shell-drawer__head">
          <span className="shell-brand__name">Campus Complaints</span>
          <button type="button" className="shell-menu-btn" onClick={() => setDrawerOpen(false)} aria-label="Close menu">
            <Icon name="close" size={22} />
          </button>
        </div>
        {nav}
      </div>

      <main className="shell-main" id="main" tabIndex={-1}>
        <div className="shell-content">{children}</div>
      </main>
    </div>
  );
}
