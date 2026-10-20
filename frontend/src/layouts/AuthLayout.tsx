import React from 'react';
import { CampusBackgroundSlideshow } from '../components/CampusBackgroundSlideshow';
import { CAMPUS_PHOTOS } from '../lib/campusPhotos';
import './AuthLayout.css';

/** Shared frame for sign-in and registration: campus photographs behind a single panel. */
export function AuthLayout({ children, centered = false }: { children: React.ReactNode; centered?: boolean }) {
  return (
    <div className={`auth-layout ${centered ? 'auth-layout--centered' : ''}`}>
      <CampusBackgroundSlideshow photos={CAMPUS_PHOTOS} />
      <main className="auth-layout__main" id="main">
        <div className="auth-panel">
          <header className="auth-panel__brand">
            <img src="/dau-logo.png" alt="Dhirubhai Ambani University" className="auth-panel__logo" width={124} height={65} />
            <p className="auth-panel__product">Campus Complaint Management System</p>
          </header>
          {children}
        </div>
      </main>
    </div>
  );
}
