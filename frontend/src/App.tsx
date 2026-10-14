import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import AuthPage from './components/AuthPage';
import SubmitComplaintForm from './components/SubmitComplaintForm';
import ComplaintReceipt from './components/ComplaintReceipt';
import MyComplaintsList from './components/MyComplaintsList';
import StaffDashboard from './components/StaffDashboard';
import AdminDashboard from './components/AdminDashboard';
import { ComplaintResponse } from './types';
import './App.css';

function MainApp() {
  const { user, isLoading, logout } = useAuth();

  // Navigation states
  const [currentView, setCurrentView] = useState<'submit' | 'mine' | 'receipt'>('submit');
  const [lastSubmittedComplaint, setLastSubmittedComplaint] = useState<ComplaintResponse | null>(null);

  // If restoring user token session
  if (isLoading) {
    return (
      <div className="app-container" style={{ justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--color-text-main)' }}>
            Connecting to CCMS Campus Server...
          </h2>
          <p style={{ marginTop: '8px', color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
            Restoring your authenticated session
          </p>
        </div>
      </div>
    );
  }

  // If not logged in, show Auth Screen
  if (!user) {
    return (
      <div className="app-container">
        <header className="top-navbar">
          <div className="navbar-brand">
            <img src="/dau-logo.png" alt="Dhirubhai Ambani University" className="header-logo" />
            <div className="brand-divider" aria-hidden="true" />
            <span className="brand-title">Campus Complaint Management System</span>
          </div>
        </header>

        <main className="main-content">
          <AuthPage />
        </main>
      </div>
    );
  }

  const handleComplaintSubmitted = (newComplaint: ComplaintResponse) => {
    setLastSubmittedComplaint(newComplaint);
    setCurrentView('receipt');
  };

  return (
    <div className="app-container">
      {/* Top University Navigation Bar */}
      <header className="top-navbar">
        <div className="navbar-brand">
          <img src="/dau-logo.png" alt="Dhirubhai Ambani University" className="header-logo" />
          <div className="brand-divider" aria-hidden="true" />
          <span className="brand-title">Campus Complaint Management System</span>
        </div>

        <nav>
          <ul className="navbar-nav">
            {/* Student Navigation */}
            {user.role === 'student' && (
              <>
                <li>
                  <button
                    type="button"
                    className={`nav-link ${currentView === 'submit' ? 'active' : ''}`}
                    onClick={() => setCurrentView('submit')}
                  >
                    Register Complaint
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className={`nav-link ${currentView === 'mine' ? 'active' : ''}`}
                    onClick={() => setCurrentView('mine')}
                  >
                    My Complaints
                  </button>
                </li>
              </>
            )}

            {/* Staff Navigation */}
            {user.role === 'staff' && (
              <li>
                <button type="button" className="nav-link active">
                  Staff Portal
                </button>
              </li>
            )}

            {/* Admin Navigation */}
            {user.role === 'admin' && (
              <li>
                <button type="button" className="nav-link active">
                  Admin Overview
                </button>
              </li>
            )}

            {/* User Session Info & Sign Out */}
            <li>
              <div className="user-badge-group">
                <span className="user-badge">
                  <span>{user.name}</span>
                  <span className="role-tag">{user.role}</span>
                </span>
                <button
                  type="button"
                  className="btn-signout"
                  onClick={logout}
                  title="Sign out of CCMS"
                >
                  Sign Out
                </button>
              </div>
            </li>
          </ul>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        <div className="content-card">
          {/* Student Role Views */}
          {user.role === 'student' && (
            <>
              {currentView === 'submit' && (
                <SubmitComplaintForm onSubmitSuccess={handleComplaintSubmitted} />
              )}

              {currentView === 'receipt' && lastSubmittedComplaint && (
                <ComplaintReceipt
                  complaint={lastSubmittedComplaint}
                  onViewMyComplaints={() => setCurrentView('mine')}
                  onRegisterAnother={() => setCurrentView('submit')}
                />
              )}

              {currentView === 'mine' && (
                <MyComplaintsList onRegisterNew={() => setCurrentView('submit')} />
              )}
            </>
          )}

          {/* Staff Role View */}
          {user.role === 'staff' && <StaffDashboard />}

          {/* Admin Role View */}
          {user.role === 'admin' && <AdminDashboard />}
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}
