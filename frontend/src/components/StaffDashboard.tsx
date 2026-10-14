import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Department } from '../types';
import { getDepartmentsApi } from '../api/departments';

export default function StaffDashboard() {
  const { user } = useAuth();
  const [departments, setDepartments] = useState<Department[]>([]);
  const [assignedDept, setAssignedDept] = useState<Department | null>(null);

  useEffect(() => {
    async function loadDept() {
      try {
        const depts = await getDepartmentsApi();
        setDepartments(depts);
        if (user?.department_id) {
          const match = depts.find((d) => d.id === user.department_id);
          setAssignedDept(match || null);
        }
      } catch {
        // Fallback
      }
    }
    loadDept();
  }, [user]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-lg)' }}>
      <div style={{ borderBottom: '1px solid var(--color-border-light)', paddingBottom: 'var(--space-md)' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--color-text-main)' }}>
          Staff Department Portal
        </h2>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.95rem', marginTop: '4px' }}>
          Authorized staff access for campus authority personnel.
        </p>
      </div>

      <div style={{ backgroundColor: 'var(--color-surface-subtle)', borderRadius: 'var(--radius-lg)', padding: 'var(--space-lg)', display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Staff Member</span>
          <span style={{ fontWeight: 700 }}>{user?.name}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Official Email</span>
          <span style={{ fontWeight: 600 }}>{user?.email}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Assigned Department</span>
          <span style={{ fontWeight: 700, color: 'var(--color-primary)' }}>
            {assignedDept ? assignedDept.name : user?.department_id ? `Department #${user.department_id}` : 'General Staff'}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Security Role</span>
          <span style={{ textTransform: 'uppercase', fontSize: '0.8rem', fontWeight: 700, backgroundColor: '#E5E7EB', padding: '2px 8px', borderRadius: '4px' }}>
            {user?.role}
          </span>
        </div>
      </div>

      <div style={{ backgroundColor: 'var(--color-advisory-bg)', borderRadius: 'var(--radius-md)', padding: 'var(--space-md)', color: '#78350F', fontSize: '0.9rem', lineHeight: '1.5' }}>
        <strong>Sprint 1 Governance Boundary:</strong>
        <p style={{ marginTop: '4px' }}>
          In accordance with the Sprint 1 requirements, complaint registration is reserved strictly for authenticated students. Staff review queues, ticket assignment, and status resolutions are scheduled for Sprint 2.
        </p>
      </div>
    </div>
  );
}
