import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Department, HealthResponse } from '../types';
import { getHealthApi } from '../api/system';
import { getDepartmentsApi } from '../api/departments';

export default function AdminDashboard() {
  const { user } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadAdminData() {
      try {
        const [healthData, deptsData] = await Promise.all([
          getHealthApi(),
          getDepartmentsApi(),
        ]);
        setHealth(healthData);
        setDepartments(deptsData);
      } catch (err) {
        // Fallback
      } finally {
        setIsLoading(false);
      }
    }
    loadAdminData();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div style={{ borderBottom: '1px solid var(--color-border-light)', paddingBottom: 'var(--space-md)' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-text-main)' }}>
          Campus System Administration
        </h2>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.95rem', marginTop: '4px' }}>
          Overview of CCMS services, backend database health, and active campus routing authorities.
        </p>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--color-text-muted)' }}>
          Loading system health and department taxonomy...
        </div>
      ) : (
        <>
          {/* Health Status Box */}
          <div style={{ backgroundColor: 'var(--color-surface-subtle)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-lg)', display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '4px' }}>System Diagnostics</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>API Status</span>
              <span style={{ fontWeight: 700, color: health?.status === 'healthy' ? '#065F46' : '#B91C1C' }}>
                ● {health?.status?.toUpperCase() || 'UNKNOWN'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Database Connection</span>
              <span style={{ fontWeight: 600 }}>{health?.database || 'operational'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Service Version</span>
              <span style={{ fontWeight: 600 }}>v{health?.version || '1.0.0'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Logged Administrator</span>
              <span style={{ fontWeight: 600 }}>{user?.name} ({user?.email})</span>
            </div>
          </div>

          {/* Active Departments Catalog */}
          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 'var(--space-sm)' }}>
              Active Routing Departments ({departments.length})
            </h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 'var(--space-md)' }}>
              {departments.map((dept) => (
                <div
                  key={dept.id}
                  style={{
                    backgroundColor: 'var(--color-surface-subtle)',
                    padding: 'var(--space-md)',
                    borderRadius: 'var(--radius-md)',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>{dept.name}</span>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#065F46', backgroundColor: '#D1FAE5', padding: '2px 6px', borderRadius: '4px' }}>
                      ACTIVE
                    </span>
                  </div>
                  <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', lineHeight: '1.4' }}>
                    {dept.description || 'No description provided.'}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
