import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import {
  DEPARTMENTS,
  HOSTEL_LOCATIONS,
  makeToken,
  makeUser,
  mockApi,
} from './mockApi';

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

const staffMember = {
  id: 7,
  name: 'Aarav Sharma',
  email: 'aarav@dau.ac.in',
  department_id: 1,
  department_name: 'Hostel',
  hostels: [{ id: 1, code: 'HA', name: 'Hostel A' }],
};

const metrics = {
  total_complaints: 0,
  status_counts: [],
  department_counts: [],
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

const baseAdmin = {
  'GET /api/v1/users/me': () => ({
    body: makeUser({ role: 'admin', name: 'Admin Officer' }),
  }),
  'GET /health': () => ({
    body: {
      status: 'healthy',
      project: 'CCMS',
      version: '2.0.0',
      environment: 'production',
      database: 'connected',
    },
  }),
  'GET /health/ready': () => ({
    body: { ready: true, database: 'connected' },
  }),
  'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
  'GET /api/v1/admin/metrics/summary': () => ({ body: metrics }),
  'GET /api/v1/admin/staff': () => ({ body: [staffMember] }),
  'GET /api/v1/locations/hostels': () => ({ body: HOSTEL_LOCATIONS }),
};

describe('Sprint 4 Admin Staff Hostel Assignments', () => {
  it('shows a loading state while staff assignments are being fetched', async () => {
    const api = mockApi(baseAdmin);
    const originalFetch = api.fetchMock.getMockImplementation();

    if (!originalFetch) {
      throw new Error('Expected mock fetch implementation');
    }

    api.fetchMock.mockImplementation((input, init) => {
      const url = new URL(
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      );

      if (
        (init?.method ?? 'GET').toUpperCase() === 'GET' &&
        url.pathname === '/api/v1/admin/staff'
      ) {
        return new Promise<Response>(() => {});
      }

      return originalFetch(input, init);
    });

    const { container } = renderAt('/admin');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /staff hostel assignments/i })).toBeInTheDocument();
    });

    expect(container.querySelector('.row-skeletons')).toBeInTheDocument();
  });

  it('displays an empty state when no staff members are returned', async () => {
    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/staff': () => ({ body: [] }),
    });

    renderAt('/admin');

    expect(
      await screen.findByText('No staff members found.')
    ).toBeInTheDocument();
  });

  it('displays an error when the staff list API fails', async () => {
    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/staff': () => ({
        status: 500,
        body: { detail: 'Staff service unavailable' },
      }),
    });

    renderAt('/admin');

    expect(
      await screen.findByText(/could not load staff members/i)
    ).toBeInTheDocument();

    expect(
      screen.getByText(/staff service unavailable/i)
    ).toBeInTheDocument();
  });

  it('saves updated hostel assignments and refreshes the staff list', async () => {
    const user = userEvent.setup();
    let currentStaff = { ...staffMember };

    const api = mockApi({
      ...baseAdmin,

      'GET /api/v1/admin/staff': () => ({
        body: [currentStaff],
      }),

      'PUT /api/v1/admin/staff/7/hostels': (req) => {
        const body = req.body as { hostel_ids: number[] };

        currentStaff = {
          ...currentStaff,
          hostels: HOSTEL_LOCATIONS
            .filter((hostel) => body.hostel_ids.includes(hostel.id))
            .map((hostel) => ({
              id: hostel.id,
              code: hostel.code,
              name: hostel.name,
            })),
        };

        return { body: currentStaff };
      },
    });

    renderAt('/admin');

    const staffCard = await screen.findByRole('article', {
      name: 'Hostel assignments for Aarav Sharma',
    });

    expect(
      within(staffCard).getByText('Department: Hostel')
    ).toBeInTheDocument();

    expect(
      within(staffCard).getByText(/currently assigned:/i)
    ).toBeInTheDocument();

    await user.click(
      within(staffCard).getByRole('checkbox', {
        name: 'Assign Hostel B to Aarav Sharma',
      })
    );

    await user.click(
      within(staffCard).getByRole('button', {
        name: 'Save assignments',
      })
    );

    await waitFor(() => {
      expect(
        api.callsTo('PUT /api/v1/admin/staff/7/hostels')
      ).toHaveLength(1);
    });

    expect(
      api.callsTo('PUT /api/v1/admin/staff/7/hostels')[0].body
    ).toEqual({ hostel_ids: [1, 2] });

    expect(
      await screen.findByRole('status')
    ).toHaveTextContent('Hostel assignments updated for Aarav Sharma.');

    await waitFor(() => {
      expect(
        api.callsTo('GET /api/v1/admin/staff').length
      ).toBeGreaterThanOrEqual(2);
    });

    expect(
      within(staffCard).getByText('Currently assigned: Hostel A, Hostel B')
    ).toBeInTheDocument();
  });
});


