import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import { DEPARTMENTS, makeToken, makeUser, mockApi } from './mockApi';
import { AdminMetricsSummary } from '../types';

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

const mockMetrics: AdminMetricsSummary = {
  total_complaints: 42,
  status_counts: [
    { status: 'submitted', count: 10 },
    { status: 'in_progress', count: 15 },
    { status: 'resolved', count: 14 },
    { status: 'reopened', count: 3 },
  ],
  department_counts: [
    { department_id: 1, department_name: 'Hostel', count: 18 },
    { department_id: 2, department_name: 'IT Services', count: 14 },
    { department_id: 3, department_name: 'Library', count: 10 },
  ],
  resolution_metrics: {
    window_days: 30,
    department_id: null,
    resolved_count: 14,
    average_resolution_hours: 24.5,
    average_resolution_days: 1.02,
    median_resolution_hours: 18.0,
    min_resolution_hours: 2.5,
    max_resolution_hours: 72.0,
  },
};

const baseAdmin = {
  'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin', name: 'Admin Officer' }) }),
  'GET /health': () => ({
    body: { status: 'healthy', project: 'CCMS', version: '2.0.0', environment: 'production', database: 'connected' },
  }),
  'GET /health/ready': () => ({ body: { ready: true, database: 'connected' } }),
  'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
  'GET /api/v1/admin/metrics/summary': () => ({ body: mockMetrics }),
};

describe('Sprint 2 Admin Workflow — Admin Metrics Dashboard', () => {
  it('loads admin metrics summary and displays complaint counts by status', async () => {
    mockApi(baseAdmin);
    renderAt('/admin');

    // Page title and header
    expect(await screen.findByRole('heading', { name: /admin metrics & system overview/i })).toBeInTheDocument();

    // Verify complaint counts by status
    expect(await screen.findByText('42')).toBeInTheDocument();

    const totalCard = screen.getByTestId('stat-total');
    expect(within(totalCard).getByText('42')).toBeInTheDocument();

    const submittedCard = screen.getByTestId('stat-submitted');
    expect(within(submittedCard).getByText('10')).toBeInTheDocument();

    const inProgressCard = screen.getByTestId('stat-in-progress');
    expect(within(inProgressCard).getByText('15')).toBeInTheDocument();

    const resolvedCard = screen.getByTestId('stat-resolved');
    expect(within(resolvedCard).getByText('14')).toBeInTheDocument();

    const reopenedCard = screen.getByTestId('stat-reopened');
    expect(within(reopenedCard).getByText('3')).toBeInTheDocument();
  });

  it('displays rolling-average resolution time and its prominent definition', async () => {
    mockApi(baseAdmin);
    renderAt('/admin');

    // Resolution metric average hours and days
    expect(await screen.findByText('24.5 hrs')).toBeInTheDocument();
    expect(screen.getByText('(~1.0 days)')).toBeInTheDocument();

    // Additional resolution duration statistics
    expect(screen.getByText('30 days')).toBeInTheDocument();
    expect(screen.getByText('14 complaints')).toBeInTheDocument();
    expect(screen.getByText('18.0 hrs')).toBeInTheDocument();
    expect(screen.getByText('2.5 hrs')).toBeInTheDocument();
    expect(screen.getByText('72.0 hrs')).toBeInTheDocument();

    // Definition must be clearly displayed on screen
    const defBox = screen.getByRole('region', { name: /metric definition/i });
    expect(defBox).toBeInTheDocument();
    expect(
      within(defBox).getByText(/mean of \(resolved_at − created_at\), in hours/i)
    ).toBeInTheDocument();
  });

  it('displays department-wise complaint breakdown', async () => {
    mockApi(baseAdmin);
    renderAt('/admin');

    const deptTable = await screen.findByRole('table', { name: /department-wise complaint counts/i });
    expect(deptTable).toBeInTheDocument();

    // Verify each department count
    const rows = within(deptTable).getAllByRole('row');
    expect(within(rows[1]).getByText('Hostel')).toBeInTheDocument();
    expect(within(rows[1]).getByText('18')).toBeInTheDocument();

    expect(within(rows[2]).getByText('IT Services')).toBeInTheDocument();
    expect(within(rows[2]).getByText('14')).toBeInTheDocument();

    expect(within(rows[3]).getByText('Library')).toBeInTheDocument();
    expect(within(rows[3]).getByText('10')).toBeInTheDocument();
  });

  it('handles empty resolution metrics gracefully when no complaints are resolved', async () => {
    const emptyMetrics: AdminMetricsSummary = {
      total_complaints: 5,
      status_counts: [
        { status: 'submitted', count: 5 },
        { status: 'in_progress', count: 0 },
        { status: 'resolved', count: 0 },
        { status: 'reopened', count: 0 },
      ],
      department_counts: [
        { department_id: 1, department_name: 'Hostel', count: 5 },
      ],
      resolution_metrics: {
        window_days: 30,
        department_id: null,
        resolved_count: 0,
        average_resolution_hours: null,
        average_resolution_days: null,
        median_resolution_hours: null,
        min_resolution_hours: null,
        max_resolution_hours: null,
      },
    };

    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/metrics/summary': () => ({ body: emptyMetrics }),
    });

    renderAt('/admin');

    expect(await screen.findByRole('heading', { name: /admin metrics & system overview/i })).toBeInTheDocument();

    // Average time should be dash when 0 complaints resolved
    expect(screen.getByText('0 complaints')).toBeInTheDocument();
  });

  it('handles API error state and allows retry with Check again button', async () => {
    let callCount = 0;
    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/metrics/summary': () => {
        callCount++;
        if (callCount === 1) {
          return { status: 500, body: { detail: 'Metrics database connection failed' } };
        }
        return { body: mockMetrics };
      },
    });

    renderAt('/admin');
    const user = userEvent.setup();

    // Error alert should be displayed
    expect(await screen.findByText(/could not load complaint metrics/i)).toBeInTheDocument();

    // Click "Check again" button
    const retryBtn = screen.getByRole('button', { name: /check again/i });
    await user.click(retryBtn);

    // After retry, metrics should load
    expect(await screen.findByText('24.5 hrs')).toBeInTheDocument();
    expect(screen.queryByText(/could not load complaint metrics/i)).not.toBeInTheDocument();
  });

  it('preserves existing system overview service health indicators and admin profile', async () => {
    mockApi(baseAdmin);
    renderAt('/admin');

    // System health indicators from Sprint 1
    expect(await screen.findByText('Healthy')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('2.0.0')).toBeInTheDocument();

    // Administrator identity
    expect(screen.getAllByText('Admin Officer').length).toBeGreaterThan(0);
  });
});
