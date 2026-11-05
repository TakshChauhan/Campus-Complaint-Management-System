import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { CoverageGapsSection } from '../components/CoverageGapsSection';
import { mockApi } from './mockApi';

describe('S4-23: Coverage gaps list frontend tests', () => {
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
