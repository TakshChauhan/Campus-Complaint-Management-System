import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import { DEPARTMENTS, HOSTEL_LOCATIONS, makeToken, makeUser, mockApi } from './mockApi';
import { FeedItem, HostelFeedItem } from '../types';

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

const mockFeedIT: FeedItem[] = [
  {
    id: 101,
    title: 'Lab 3 Wi-Fi connection dropping repeatedly',
    department_id: 2,
    department_name: 'IT Services',
    status: 'in_progress',
    created_at: '2026-10-25T14:30:00Z',
    updated_at: '2026-10-26T09:00:00Z',
    reopen_count: 0,
  },
  {
    id: 102,
    title: 'Library printer paper jam',
    department_id: 3,
    department_name: 'Library',
    status: 'resolved',
    created_at: '2026-10-24T11:00:00Z',
    updated_at: '2026-10-25T16:00:00Z',
    reopen_count: 1,
  },
];

const mockFeedHostel: HostelFeedItem[] = [
  {
    id: 103,
    title: 'Water cooler leaking near water station',
    department_id: 1,
    department_name: 'Hostel',
    status: 'submitted',
    created_at: '2026-10-27T08:15:00Z',
    updated_at: '2026-10-27T08:15:00Z',
    reopen_count: 0,
    hostel: 'Hostel A',
    wing: 'East Wing',
    floor: 'Second Floor',
  },
  {
    id: 104,
    title: 'Corridor light fixture flickering',
    department_id: 1,
    department_name: 'Hostel',
    status: 'reopened',
    created_at: '2026-10-23T19:00:00Z',
    updated_at: '2026-10-26T12:00:00Z',
    reopen_count: 2,
    hostel: 'Hostel B',
    wing: 'South Wing',
    floor: 'Ground Floor',
  },
];

const baseHandlers = {
  'GET /api/v1/users/me': () => ({ body: makeUser() }),
  'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
  'GET /api/v1/locations/hostels': () => ({ body: HOSTEL_LOCATIONS }),
  'GET /api/v1/feeds/departments/2': () => ({ body: [mockFeedIT[0]] }),
  'GET /api/v1/feeds/departments/3': () => ({ body: [mockFeedIT[1]] }),
  'GET /api/v1/feeds/hostel': () => ({ body: mockFeedHostel }),
};

describe('Campus Public Feed (Dev Task B Takeover)', () => {
  it('renders published complaints and verifies privacy protection (no student names or emails)', async () => {
    mockApi(baseHandlers);
    renderAt('/feed');

    // Page title and privacy banner
    expect(await screen.findByRole('heading', { name: /campus public feed/i })).toBeInTheDocument();
    expect(screen.getByText(/personal identifiers \(names, email addresses, and roll numbers\) are never exposed/i)).toBeInTheDocument();

    // Verify complaint items are displayed
    expect(await screen.findByText('Water cooler leaking near water station')).toBeInTheDocument();
    expect(screen.getByText('Lab 3 Wi-Fi connection dropping repeatedly')).toBeInTheDocument();
    expect(screen.getByText('Library printer paper jam')).toBeInTheDocument();
    expect(screen.getByText('Corridor light fixture flickering')).toBeInTheDocument();

    // Verify departments and statuses
    expect(screen.getAllByText('IT Services').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Hostel').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Library').length).toBeGreaterThan(0);

    // Verify locations are shown when present
    expect(screen.getByText('Hostel A • East Wing • Second Floor')).toBeInTheDocument();

    // Verify reopened tag
    expect(screen.getByText('Reopened 2x')).toBeInTheDocument();

    // STRICT PRIVACY CHECK: Ensure reporter identity and emails are NEVER in the feed cards
    const feedContainer = screen.getByRole('feed', { name: /campus public complaints/i });
    expect(within(feedContainer).queryByText(/202401001@dau\.ac\.in/i)).not.toBeInTheDocument();
    expect(within(feedContainer).queryByText(/Aarav Patel/i)).not.toBeInTheDocument();
    expect(within(feedContainer).queryByText(/reporter/i)).not.toBeInTheDocument();
    expect(within(feedContainer).queryByText(/student/i)).not.toBeInTheDocument();
  });

  it('filters complaints by department', async () => {
    const user = userEvent.setup();
    mockApi(baseHandlers);
    renderAt('/feed');

    // Wait for all to load
    await screen.findByText('Water cooler leaking near water station');

    // Filter by IT Services (id = 2)
    const deptSelect = screen.getByLabelText(/department/i);
    await user.selectOptions(deptSelect, '2');

    // Only IT Services complaint should be shown
    await waitFor(() => {
      expect(screen.getByText('Lab 3 Wi-Fi connection dropping repeatedly')).toBeInTheDocument();
      expect(screen.queryByText('Water cooler leaking near water station')).not.toBeInTheDocument();
      expect(screen.queryByText('Library printer paper jam')).not.toBeInTheDocument();
    });
  });

  it('filters complaints by location (Hostel, Wing, Floor)', async () => {
    const user = userEvent.setup();
    mockApi(baseHandlers);
    renderAt('/feed');

    await screen.findByText('Water cooler leaking near water station');

    // Select Hostel A
    const hostelSelect = screen.getByLabelText(/^hostel$/i);
    await user.selectOptions(hostelSelect, 'Hostel A');

    // Hostel A complaints visible, Hostel B hidden
    expect(screen.getByText('Water cooler leaking near water station')).toBeInTheDocument();
    expect(screen.queryByText('Corridor light fixture flickering')).not.toBeInTheDocument();

    // Select East Wing
    const wingSelect = screen.getByLabelText(/^wing$/i);
    await user.selectOptions(wingSelect, 'East Wing');

    // Select Second Floor
    const floorSelect = screen.getByLabelText(/^floor$/i);
    await user.selectOptions(floorSelect, 'Second Floor');

    expect(screen.getByText('Water cooler leaking near water station')).toBeInTheDocument();
  });

  it('filters complaints by status', async () => {
    const user = userEvent.setup();
    mockApi({
      ...baseHandlers,
      'GET /api/v1/feeds/departments/2': (req) => {
        const status = req.url.searchParams.get('status');
        if (status === 'resolved') return { body: [] };
        return { body: [mockFeedIT[0]] };
      },
      'GET /api/v1/feeds/departments/3': (req) => {
        const status = req.url.searchParams.get('status');
        if (status === 'resolved') return { body: [mockFeedIT[1]] };
        return { body: [] };
      },
      'GET /api/v1/feeds/hostel': (req) => {
        const status = req.url.searchParams.get('status');
        if (status === 'resolved') return { body: [] };
        return { body: mockFeedHostel };
      },
    });
    renderAt('/feed');

    await screen.findByText('Water cooler leaking near water station');

    // Select Resolved status
    const statusSelect = screen.getByLabelText(/status/i);
    await user.selectOptions(statusSelect, 'resolved');

    await waitFor(() => {
      expect(screen.getByText('Library printer paper jam')).toBeInTheDocument();
      expect(screen.queryByText('Water cooler leaking near water station')).not.toBeInTheDocument();
    });
  });

  it('resets filters when clicking Clear all filters', async () => {
    const user = userEvent.setup();
    mockApi(baseHandlers);
    renderAt('/feed');

    await screen.findByText('Water cooler leaking near water station');

    // Search for something nonexistent
    const searchInput = screen.getByLabelText(/search title or #id/i);
    await user.type(searchInput, 'nonexistentquery123');

    // Should show empty state
    expect(await screen.findByText('No matching public complaints')).toBeInTheDocument();

    // Click "Clear all filters"
    const clearButton = screen.getAllByRole('button', { name: /clear all filters/i })[0];
    await user.click(clearButton);

    // Everything restored
    expect(await screen.findByText('Water cooler leaking near water station')).toBeInTheDocument();
    expect(screen.getByText('Lab 3 Wi-Fi connection dropping repeatedly')).toBeInTheDocument();
  });

  it('handles error state and retries successfully', async () => {
    const user = userEvent.setup();
    let fail = true;
    mockApi({
      ...baseHandlers,
      'GET /api/v1/feeds/departments/2': () => {
        if (fail) return { status: 500, body: { detail: 'Feed unavailable right now' } };
        return { body: [mockFeedIT[0]] };
      },
      'GET /api/v1/feeds/departments/3': () => {
        if (fail) return { status: 500, body: { detail: 'Feed unavailable right now' } };
        return { body: [mockFeedIT[1]] };
      },
      'GET /api/v1/feeds/hostel': () => {
        if (fail) return { status: 500, body: { detail: 'Feed unavailable right now' } };
        return { body: mockFeedHostel };
      },
    });

    renderAt('/feed');

    // Check error alert is displayed
    expect(await screen.findByText(/Feed unavailable right now/i)).toBeInTheDocument();

    // Now make it succeed and click Retry
    fail = false;
    const retryBtn = screen.getByRole('button', { name: /retry/i });
    await user.click(retryBtn);

    // Content appears
    expect(await screen.findByText('Water cooler leaking near water station')).toBeInTheDocument();
  });
});
