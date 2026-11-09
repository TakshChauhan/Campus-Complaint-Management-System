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
    mockApi({
      ...baseHandlers,
      'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin' }) }),
    });
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

  describe('Task S4-12 Student Scope Toggle and Requests', () => {
    it('sends scope=hostel by default and never sends hostel_id for students', async () => {
      const api = mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'student' }) }),
      });
      renderAt('/feed');

      await screen.findByText('Water cooler leaking near water station');

      const hostelCalls = api.callsTo('GET /api/v1/feeds/hostel');
      expect(hostelCalls.length).toBeGreaterThan(0);
      const firstCall = hostelCalls[0];
      expect(firstCall.url.searchParams.get('scope')).toBe('hostel');
      expect(firstCall.url.searchParams.get('hostel_id')).toBeNull();

      // Students cannot choose a hostel
      expect(screen.queryByLabelText(/^hostel$/i, { selector: 'select' })).not.toBeInTheDocument();
      expect(screen.queryByRole('combobox', { name: /^hostel$/i })).not.toBeInTheDocument();
    });

    it('updates scope and sends scope=wing or scope=floor on toggle without hostel_id', async () => {
      const user = userEvent.setup();
      const api = mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'student' }) }),
      });
      renderAt('/feed');

      await screen.findByText('Water cooler leaking near water station');

      // Click "My Wing"
      const wingRadio = screen.getByRole('radio', { name: /my wing/i });
      await user.click(wingRadio);

      await waitFor(() => {
        const lastCall = api.callsTo('GET /api/v1/feeds/hostel').slice(-1)[0];
        expect(lastCall.url.searchParams.get('scope')).toBe('wing');
        expect(lastCall.url.searchParams.get('hostel_id')).toBeNull();
      });

      // Click "My Floor"
      const floorRadio = screen.getByRole('radio', { name: /my floor/i });
      await user.click(floorRadio);

      await waitFor(() => {
        const lastCall = api.callsTo('GET /api/v1/feeds/hostel').slice(-1)[0];
        expect(lastCall.url.searchParams.get('scope')).toBe('floor');
        expect(lastCall.url.searchParams.get('hostel_id')).toBeNull();
      });

      // Click "Hostel"
      const hostelRadio = screen.getByRole('radio', { name: /^hostel$/i });
      await user.click(hostelRadio);

      await waitFor(() => {
        const lastCall = api.callsTo('GET /api/v1/feeds/hostel').slice(-1)[0];
        expect(lastCall.url.searchParams.get('scope')).toBe('hostel');
        expect(lastCall.url.searchParams.get('hostel_id')).toBeNull();
      });
    });
  });

  describe('Task S4-12 Staff and Admin Scoping', () => {
    it('staff requests include numeric hostel_id and no scope', async () => {
      const user = userEvent.setup();
      const api = mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'staff', department_id: 1 }) }),
      });
      renderAt('/feed');

      await screen.findByText('Water cooler leaking near water station');

      // Staff cannot see the student scope radio group
      expect(screen.queryByRole('radiogroup', { name: /hostel feed scope/i })).not.toBeInTheDocument();

      // Staff sees the Hostel dropdown
      const hostelSelect = screen.getByLabelText(/^hostel$/i);
      expect(hostelSelect).toBeInTheDocument();

      // Select Hostel B (id = 2)
      await user.selectOptions(hostelSelect, 'Hostel B');

      await waitFor(() => {
        const hostelCalls = api.callsTo('GET /api/v1/feeds/hostel');
        const lastCall = hostelCalls[hostelCalls.length - 1];
        expect(lastCall.url.searchParams.get('hostel_id')).toBe('2');
        expect(lastCall.url.searchParams.get('scope')).toBeNull();
      });
    });

    it('admin requests include numeric hostel_id and no scope', async () => {
      const user = userEvent.setup();
      const api = mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin' }) }),
      });
      renderAt('/feed');

      await screen.findByText('Water cooler leaking near water station');

      expect(screen.queryByRole('radiogroup', { name: /hostel feed scope/i })).not.toBeInTheDocument();
      const hostelSelect = screen.getByLabelText(/^hostel$/i);
      await user.selectOptions(hostelSelect, 'Hostel A');

      await waitFor(() => {
        const hostelCalls = api.callsTo('GET /api/v1/feeds/hostel');
        const lastCall = hostelCalls[hostelCalls.length - 1];
        expect(lastCall.url.searchParams.get('hostel_id')).toBe('1');
        expect(lastCall.url.searchParams.get('scope')).toBeNull();
      });
    });
  });

  describe('Task S4-12 All Departments Aggregation, Ordering, and Deduplication', () => {
    it('aggregates across departments, dedupes complaint IDs, and sorts chronologically', async () => {
      const itemDept2 = {
        id: 501,
        title: 'Older IT complaint',
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: '2026-10-20T10:00:00Z',
        updated_at: '2026-10-20T10:00:00Z',
        reopen_count: 0,
      };
      const itemDept3 = {
        id: 502,
        title: 'Newest Library complaint',
        department_id: 3,
        department_name: 'Library',
        status: 'submitted',
        created_at: '2026-10-25T10:00:00Z',
        updated_at: '2026-10-25T10:00:00Z',
        reopen_count: 0,
      };
      const itemHostel = {
        id: 503,
        title: 'Middle Hostel complaint',
        department_id: 1,
        department_name: 'Hostel',
        status: 'submitted',
        created_at: '2026-10-22T10:00:00Z',
        updated_at: '2026-10-22T10:00:00Z',
        reopen_count: 0,
        hostel: 'Hostel A',
        wing: 'East Wing',
        floor: 'First Floor',
      };
      // Duplicate of 501 appearing in another feed
      const duplicate501 = { ...itemDept2 };

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({ body: [itemDept2] }),
        'GET /api/v1/feeds/departments/3': () => ({ body: [itemDept3, duplicate501] }),
        'GET /api/v1/feeds/hostel': () => ({ body: [itemHostel] }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Newest Library complaint')).toBeInTheDocument();
      expect(screen.getByText('Middle Hostel complaint')).toBeInTheDocument();
      expect(screen.getByText('Older IT complaint')).toBeInTheDocument();

      // Ensure duplicate item 501 appears only once in the feed list
      const feed = screen.getByRole('feed', { name: /campus public complaints/i });
      expect(within(feed).getAllByText('Older IT complaint')).toHaveLength(1);

      // Verify chronological ordering in the DOM
      const titles = within(feed).getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
      expect(titles).toEqual([
        'Newest Library complaint',
        'Middle Hostel complaint',
        'Older IT complaint',
      ]);
    });
  });

  describe('Task S4-12 Pagination and Stale Request Protection', () => {
    it('supports Next and Previous pagination and displays Page X of Y', async () => {
      const user = userEvent.setup();
      // Generate 12 items for IT Services to test 2 pages (PAGE_SIZE = 10)
      const manyItems = Array.from({ length: 12 }, (_, i) => ({
        id: 600 - i,
        title: `Paging item ${600 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28 - i).toISOString(),
        updated_at: new Date(2026, 9, 28 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: manyItems.slice(0, limit),
            headers: { 'X-Total-Count': String(manyItems.length) },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Paging item 600')).toBeInTheDocument();
      expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

      const prevBtn = screen.getByRole('button', { name: /previous/i });
      const nextBtn = screen.getByRole('button', { name: /next/i });
      expect(prevBtn).toBeDisabled();
      expect(nextBtn).toBeEnabled();

      // Navigate to Page 2
      await user.click(nextBtn);

      expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument();
      expect(screen.getByText('Paging item 589')).toBeInTheDocument();
      expect(screen.queryByText('Paging item 600')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled();
      expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();

      // Navigate back to Page 1
      await user.click(screen.getByRole('button', { name: /previous/i }));

      expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();
      expect(screen.getByText('Paging item 600')).toBeInTheDocument();
    });

    it('resets page to 1 when filters or scope change', async () => {
      const user = userEvent.setup();
      const manyItems = Array.from({ length: 15 }, (_, i) => ({
        id: 700 - i,
        title: `Filter reset item ${700 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28 - i).toISOString(),
        updated_at: new Date(2026, 9, 28 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: manyItems.slice(0, limit),
            headers: { 'X-Total-Count': String(manyItems.length) },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument();

      // Change status filter -> should reset to Page 1
      const statusSelect = screen.getByLabelText(/status/i);
      await user.selectOptions(statusSelect, 'submitted');

      expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();

      // Advance to Page 2 again
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument();

      // Change scope toggle -> should reset to Page 1
      const wingRadio = screen.getByRole('radio', { name: /my wing/i });
      await user.click(wingRadio);

      expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();
    });

    it('ignores stale older responses that complete after a newer request', async () => {
      const user = userEvent.setup();
      let resolveFirstCall: () => void = () => {};
      const gate = new Promise<void>((resolve) => {
        resolveFirstCall = resolve;
      });

      const api = mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({ body: [] }),
        'GET /api/v1/feeds/departments/3': () => ({ body: [] }),
        'GET /api/v1/feeds/hostel': (req) => {
          const scope = req.url.searchParams.get('scope');
          if (scope === 'hostel') {
            return {
              body: [
                {
                  id: 801,
                  title: 'Old Stale Hostel Complaint',
                  department_id: 1,
                  department_name: 'Hostel',
                  status: 'submitted',
                  created_at: '2026-10-20T10:00:00Z',
                  updated_at: '2026-10-20T10:00:00Z',
                  reopen_count: 0,
                  hostel: 'Hostel A',
                  wing: 'East Wing',
                  floor: 'First Floor',
                },
              ],
            };
          }
          return {
            body: [
              {
                id: 802,
                title: 'New Fresh Wing Complaint',
                department_id: 1,
                department_name: 'Hostel',
                status: 'submitted',
                created_at: '2026-10-25T10:00:00Z',
                updated_at: '2026-10-25T10:00:00Z',
                reopen_count: 0,
                hostel: 'Hostel A',
                wing: 'East Wing',
                floor: 'First Floor',
              },
            ],
          };
        },
      });

      // Pause the first scope=hostel call until gate resolves
      const originalFetch = api.fetchMock.getMockImplementation()!;
      let intercepted = false;
      api.fetchMock.mockImplementation(async (input, init) => {
        const url = String(input);
        if (url.includes('scope=hostel') && !intercepted) {
          intercepted = true;
          await gate;
        }
        return originalFetch(input, init);
      });

      renderAt('/feed');

      // Now switch scope to "my wing", triggering the faster second call
      const wingRadio = await screen.findByRole('radio', { name: /my wing/i });
      await user.click(wingRadio);

      // Call 2 completes and displays new fresh complaint
      expect(await screen.findByText('New Fresh Wing Complaint')).toBeInTheDocument();

      // Now let call 1 finish
      resolveFirstCall();

      // Give event loop time to process call 1 resolution
      await new Promise((r) => setTimeout(r, 50));

      // Old stale complaint must NOT overwrite the new data
      expect(screen.queryByText('Old Stale Hostel Complaint')).not.toBeInTheDocument();
      expect(screen.getByText('New Fresh Wing Complaint')).toBeInTheDocument();
    });
  });
});
