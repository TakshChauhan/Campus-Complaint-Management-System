import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import App from '../App';
import { setStoredToken } from '../api/client';
import { CoverageGapsSection } from '../components/CoverageGapsSection';
import { DEPARTMENTS, HOSTEL_LOCATIONS, makeToken, makeUser, mockApi } from './mockApi';

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

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
  'GET /api/v1/admin/metrics/summary': () => ({
    body: {
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
    },
  }),
  'GET /api/v1/admin/staff': () => ({ body: [] }),
  'GET /api/v1/locations/hostels': () => ({ body: HOSTEL_LOCATIONS }),
};

describe('S4-23: Coverage gaps list component tests', () => {
  it('renders loading state initially', () => {
    mockApi({
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 200,
        body: [],
      }),
    });

    render(<CoverageGapsSection />);
    expect(screen.getByLabelText('Loading coverage gaps')).toBeInTheDocument();
  });

  it('renders empty state when there are no coverage gaps', async () => {
    mockApi({
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 200,
        body: [],
      }),
    });

    render(<CoverageGapsSection />);

    await waitFor(() => {
      expect(
        screen.getByText('No coverage gaps. All hostels with open complaints have assigned staff.')
      ).toBeInTheDocument();
    });
    expect(screen.getByText('Hostel coverage gaps (0)')).toBeInTheDocument();
  });

  it('renders error state when backend API fails', async () => {
    mockApi({
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 500,
        body: { detail: 'Database error' },
      }),
    });

    render(<CoverageGapsSection />);

    await waitFor(() => {
      expect(screen.getByText(/Coverage gaps could not be loaded/)).toBeInTheDocument();
    });
  });

  it('renders one or more hostels with open complaints count', async () => {
    mockApi({
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 200,
        body: [
          {
            hostel_id: 1,
            hostel_name: 'Old Hostel for Men',
            open_count: 5,
          },
          {
            hostel_id: 2,
            hostel_name: 'New Hostel for Men',
            open_count: 2,
          },
        ],
      }),
    });

    render(<CoverageGapsSection />);

    await waitFor(() => {
      expect(screen.getByText('Old Hostel for Men')).toBeInTheDocument();
    });
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('New Hostel for Men')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Hostel coverage gaps (2)')).toBeInTheDocument();
  });
});

describe('S4-22/S4-23: Coverage gaps mounted on AdminDashboard tests', () => {
  it('renders loading state on AdminDashboard initially', async () => {
    const api = mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 200,
        body: [],
      }),
    });

    const originalFetch = api.fetchMock.getMockImplementation();
    if (!originalFetch) throw new Error('Expected mock fetch implementation');

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
        url.pathname === '/api/v1/admin/coverage-gaps'
      ) {
        return new Promise<Response>(() => {});
      }

      return originalFetch(input, init);
    });

    renderAt('/admin');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /admin metrics & system overview/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Loading coverage gaps')).toBeInTheDocument();
  });

  it('renders empty state on AdminDashboard when there are no gaps', async () => {
    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 200,
        body: [],
      }),
    });

    renderAt('/admin');

    await waitFor(() => {
      expect(
        screen.getByText('No coverage gaps. All hostels with open complaints have assigned staff.')
      ).toBeInTheDocument();
    });
    expect(screen.getByText('Hostel coverage gaps (0)')).toBeInTheDocument();
  });

  it('renders error state on AdminDashboard when coverage-gaps API fails', async () => {
    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 500,
        body: { detail: 'Service unavailable' },
      }),
    });

    renderAt('/admin');

    await waitFor(() => {
      expect(screen.getByText(/Coverage gaps could not be loaded/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Service unavailable/)).toBeInTheDocument();
  });

  it('renders coverage gaps table on AdminDashboard with unstaffed hostels and counts', async () => {
    mockApi({
      ...baseAdmin,
      'GET /api/v1/admin/coverage-gaps': () => ({
        status: 200,
        body: [
          { hostel_id: 1, hostel_name: 'Old Hostel for Men', open_count: 7 },
          { hostel_id: 3, hostel_name: 'Hostel for Women', open_count: 3 },
        ],
      }),
    });

    renderAt('/admin');

    const table = await screen.findByRole('table', {
      name: /Hostels with open complaints and no assigned staff/i,
    });
    expect(table).toBeInTheDocument();

    const rows = within(table).getAllByRole('row');
    expect(within(rows[1]).getByText('Old Hostel for Men')).toBeInTheDocument();
    expect(within(rows[1]).getByText('7')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Hostel for Women')).toBeInTheDocument();
    expect(within(rows[2]).getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Hostel coverage gaps (2)')).toBeInTheDocument();
  });
});
