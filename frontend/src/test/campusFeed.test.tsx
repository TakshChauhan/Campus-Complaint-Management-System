import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { ApiClientError, setStoredToken } from '../api/client';
import * as feedsApi from '../api/feeds';
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
    const deptSelect = screen.getByLabelText(/^department$/i, { selector: 'select' });
    await user.selectOptions(deptSelect, '2');

    // Only IT Services complaint should be shown
    await waitFor(() => {
      expect(screen.getByText('Lab 3 Wi-Fi connection dropping repeatedly')).toBeInTheDocument();
      expect(screen.queryByText('Water cooler leaking near water station')).not.toBeInTheDocument();
      expect(screen.queryByText('Library printer paper jam')).not.toBeInTheDocument();
    });
  });

  it('filters complaints by location for staff and admin via hostel_id', async () => {
    const user = userEvent.setup();
    let requestedHostelId: string | null = null;
    mockApi({
      ...baseHandlers,
      'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin' }) }),
      'GET /api/v1/feeds/hostel': (req) => {
        requestedHostelId = req.url.searchParams.get('hostel_id');
        if (requestedHostelId === '1') {
          return { body: [mockFeedHostel[0]] }; // Hostel A only
        }
        return { body: mockFeedHostel };
      },
    });
    renderAt('/feed');

    await screen.findByText('Water cooler leaking near water station');
    expect(screen.getByText('Corridor light fixture flickering')).toBeInTheDocument();

    // Select Hostel A (value="1")
    const hostelSelect = screen.getByLabelText(/^hostel$/i, { selector: 'select' });
    await user.selectOptions(hostelSelect, '1');

    // Server requested with hostel_id=1
    await waitFor(() => {
      expect(requestedHostelId).toBe('1');
    });

    // Hostel A complaint visible, Hostel B hidden
    expect(await screen.findByText('Water cooler leaking near water station')).toBeInTheDocument();
    expect(screen.queryByText('Corridor light fixture flickering')).not.toBeInTheDocument();
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
    const statusSelect = screen.getByLabelText(/^status$/i, { selector: 'select' });
    await user.selectOptions(statusSelect, 'resolved');

    await waitFor(() => {
      expect(screen.getByText('Library printer paper jam')).toBeInTheDocument();
      expect(screen.queryByText('Water cooler leaking near water station')).not.toBeInTheDocument();
    });
  });

  it('resets filters when clicking Clear all filters', async () => {
    const user = userEvent.setup();
    mockApi({
      ...baseHandlers,
      'GET /api/v1/feeds/departments/2': (req) => {
        const status = req.url.searchParams.get('status');
        if (status === 'resolved') return { body: [] };
        return { body: [mockFeedIT[0]] };
      },
      'GET /api/v1/feeds/hostel': (req) => {
        const status = req.url.searchParams.get('status');
        if (status === 'resolved') return { body: [] };
        return { body: mockFeedHostel };
      },
    });
    renderAt('/feed');

    await screen.findByText('Water cooler leaking near water station');

    // Select Status "resolved" (which only has Library printer paper jam)
    const statusSelect = screen.getByLabelText(/^status$/i, { selector: 'select' });
    await user.selectOptions(statusSelect, 'resolved');

    expect(await screen.findByText('Library printer paper jam')).toBeInTheDocument();
    expect(screen.queryByText('Water cooler leaking near water station')).not.toBeInTheDocument();

    // Click "Clear all filters"
    const clearButtons = screen.getAllByRole('button', { name: /clear all filters/i });
    await user.click(clearButtons[0]);

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
    it('renders scope toggle for students with Hostel selected by default and sends scope=hostel without hostel_id', async () => {
      let requestedScope: string | null = null;
      let requestedHostelId: string | null = null;

      mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'student' }) }),
        'GET /api/v1/feeds/hostel': (req) => {
          requestedScope = req.url.searchParams.get('scope');
          requestedHostelId = req.url.searchParams.get('hostel_id');
          return { body: mockFeedHostel };
        },
      });

      renderAt('/feed');

      await screen.findByText('Water cooler leaking near water station');

      const scopeGroup = screen.getByRole('radiogroup', { name: /hostel feed scope/i });
      expect(scopeGroup).toBeInTheDocument();

      const hostelRadio = screen.getByRole('radio', { name: /^hostel$/i });
      const wingRadio = screen.getByRole('radio', { name: /my wing/i });
      const floorRadio = screen.getByRole('radio', { name: /my floor/i });

      expect(hostelRadio).toBeChecked();
      expect(wingRadio).not.toBeChecked();
      expect(floorRadio).not.toBeChecked();

      expect(requestedScope).toBe('hostel');
      expect(requestedHostelId).toBeNull();
      expect(screen.queryByLabelText(/^hostel$/i, { selector: 'select' })).not.toBeInTheDocument();
    });

    it('updates scope and sends scope=wing or scope=floor on toggle without hostel_id', async () => {
      const user = userEvent.setup();
      let requestedScope: string | null = null;
      let requestedHostelId: string | null = null;

      mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'student' }) }),
        'GET /api/v1/feeds/hostel': (req) => {
          requestedScope = req.url.searchParams.get('scope');
          requestedHostelId = req.url.searchParams.get('hostel_id');
          return { body: mockFeedHostel };
        },
      });

      renderAt('/feed');
      await screen.findByText('Water cooler leaking near water station');

      const wingRadio = screen.getByRole('radio', { name: /my wing/i });
      await user.click(wingRadio);

      await waitFor(() => {
        expect(requestedScope).toBe('wing');
        expect(requestedHostelId).toBeNull();
      });

      const floorRadio = screen.getByRole('radio', { name: /my floor/i });
      await user.click(floorRadio);

      await waitFor(() => {
        expect(requestedScope).toBe('floor');
        expect(requestedHostelId).toBeNull();
      });
    });

    it('does not render scope toggle for staff or admin, but renders hostel selector and sends hostel_id', async () => {
      const user = userEvent.setup();
      let requestedScope: string | null = null;
      let requestedHostelId: string | null = null;

      mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'staff' }) }),
        'GET /api/v1/feeds/hostel': (req) => {
          requestedScope = req.url.searchParams.get('scope');
          requestedHostelId = req.url.searchParams.get('hostel_id');
          return { body: mockFeedHostel };
        },
      });

      renderAt('/feed');
      await screen.findByText('Water cooler leaking near water station');

      expect(screen.queryByRole('radiogroup', { name: /hostel feed scope/i })).not.toBeInTheDocument();

      const hostelSelect = screen.getByLabelText(/^hostel$/i, { selector: 'select' });
      expect(hostelSelect).toBeInTheDocument();
      expect(requestedScope).toBeNull();
      expect(requestedHostelId).toBeNull();

      await user.selectOptions(hostelSelect, '1');

      await waitFor(() => {
        expect(requestedHostelId).toBe('1');
        expect(requestedScope).toBeNull();
      });
    });

    it('admin requests include numeric hostel_id and no scope', async () => {
      const user = userEvent.setup();
      let requestedScope: string | null = null;
      let requestedHostelId: string | null = null;

      mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin' }) }),
        'GET /api/v1/feeds/hostel': (req) => {
          requestedScope = req.url.searchParams.get('scope');
          requestedHostelId = req.url.searchParams.get('hostel_id');
          return { body: mockFeedHostel };
        },
      });

      renderAt('/feed');
      await screen.findByText('Water cooler leaking near water station');

      expect(screen.queryByRole('radiogroup', { name: /hostel feed scope/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('radio', { name: /^hostel$/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('radio', { name: /my wing/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('radio', { name: /my floor/i })).not.toBeInTheDocument();

      const hostelSelect = screen.getByLabelText(/^hostel$/i, { selector: 'select' });
      expect(hostelSelect).toBeInTheDocument();
      expect(requestedScope).toBeNull();
      expect(requestedHostelId).toBeNull();

      await user.selectOptions(hostelSelect, '1');

      await waitFor(() => {
        expect(requestedHostelId).toBe('1');
        expect(requestedScope).toBeNull();
      });

      expect(screen.queryByRole('radiogroup', { name: /hostel feed scope/i })).not.toBeInTheDocument();
    });

    it('merges multiple department feeds and sorts them chronologically in All Departments view', async () => {
      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({
          body: [
            {
              id: 501,
              title: 'Older IT item',
              department_id: 2,
              department_name: 'IT Services',
              status: 'submitted',
              created_at: '2026-10-20T10:00:00Z',
              updated_at: '2026-10-20T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/departments/3': () => ({
          body: [
            {
              id: 502,
              title: 'Newest Library item',
              department_id: 3,
              department_name: 'Library',
              status: 'submitted',
              created_at: '2026-10-30T10:00:00Z',
              updated_at: '2026-10-30T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/hostel': () => ({
          body: [
            {
              id: 503,
              title: 'Middle Hostel item',
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
        }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Newest Library item')).toBeInTheDocument();

      const feedContainer = screen.getByRole('feed', { name: /campus public complaints/i });
      const cards = within(feedContainer).getAllByRole('heading', { level: 2 });
      const cardTitles = cards.map((c) => c.textContent);

      expect(cardTitles).toEqual([
        'Newest Library item',
        'Middle Hostel item',
        'Older IT item',
      ]);
    });

    it('deduplicates complaints with identical IDs across department feeds', async () => {
      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({
          body: [
            {
              id: 555,
              title: 'Duplicate Title A',
              department_id: 2,
              department_name: 'IT Services',
              status: 'submitted',
              created_at: '2026-10-25T10:00:00Z',
              updated_at: '2026-10-25T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/departments/3': () => ({
          body: [
            {
              id: 555,
              title: 'Duplicate Title B',
              department_id: 3,
              department_name: 'Library',
              status: 'submitted',
              created_at: '2026-10-25T10:00:00Z',
              updated_at: '2026-10-25T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/hostel': () => ({ body: [] }),
      });

      renderAt('/feed');

      await screen.findByText(/Duplicate Title/);
      const feedContainer = screen.getByRole('feed', { name: /campus public complaints/i });
      const cards = within(feedContainer).getAllByRole('heading', { level: 2 });
      expect(cards.length).toBe(1);
    });

    it('supports Next and Previous pagination controls with Page X of Y', async () => {
      const user = userEvent.setup();
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
      const statusSelect = screen.getByLabelText(/^status$/i, { selector: 'select' });
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

    it('shows loading state while changing pages and does not show old page items as current', async () => {
      const user = userEvent.setup();
      let resolveSecondPage: () => void = () => {};
      const page2Gate = new Promise<void>((resolve) => {
        resolveSecondPage = resolve;
      });

      const manyItems = Array.from({ length: 20 }, (_, i) => ({
        id: 900 - i,
        title: `Complaint Page Item ${900 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      const api = mockApi({
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

      const originalFetch = api.fetchMock.getMockImplementation()!;
      api.fetchMock.mockImplementation(async (input, init) => {
        const url = String(input);
        if (url.includes('limit=20')) {
          await page2Gate;
        }
        return originalFetch(input, init);
      });

      renderAt('/feed');

      // Page 1 is displayed with first item
      expect(await screen.findByText('Complaint Page Item 900')).toBeInTheDocument();
      expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

      // Click Next to request page 2
      const nextBtn = screen.getByRole('button', { name: /next/i });
      await user.click(nextBtn);

      // Loading state is active: old item is NOT shown, loading skeleton/busy is present
      expect(screen.getByText('Loading complaints...')).toBeInTheDocument();
      expect(screen.queryByText('Complaint Page Item 900')).not.toBeInTheDocument();

      // Let second page resolve
      resolveSecondPage();

      // Page 2 displays with second page item
      expect(await screen.findByText('Complaint Page Item 890')).toBeInTheDocument();
      expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    });

    it('renders empty state when there are no complaints, and after a filter change returning nothing', async () => {
      const user = userEvent.setup();
      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');

      // Default empty state when no filters are active
      expect(await screen.findByText('No public complaints published yet')).toBeInTheDocument();

      // Apply a filter (status)
      const statusSelect = screen.getByLabelText(/^status$/i, { selector: 'select' });
      await user.selectOptions(statusSelect, 'in_progress');

      // Filtered empty state with Clear all filters button
      expect(await screen.findByText('No matching public complaints')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /clear all filters/i }).length).toBeGreaterThan(0);
    });

    it('shows error on page navigation failure and Retry re-requests the same page successfully', async () => {
      const user = userEvent.setup();
      let failPage2 = true;

      const manyItems = Array.from({ length: 20 }, (_, i) => ({
        id: 950 - i,
        title: `Retry Page Item ${950 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          if (limit > 10 && failPage2) {
            return { status: 500, body: { detail: 'Server failed on page 2' } };
          }
          return {
            body: manyItems.slice(0, limit),
            headers: { 'X-Total-Count': String(manyItems.length) },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Retry Page Item 950')).toBeInTheDocument();
      expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();

      // Advance to page 2 (which fails)
      await user.click(screen.getByRole('button', { name: /next/i }));

      // Error alert is displayed
      expect(await screen.findByText(/Server failed on page 2/i)).toBeInTheDocument();
      expect(screen.queryByText('Retry Page Item 950')).not.toBeInTheDocument();

      // Make subsequent call succeed and click Retry
      failPage2 = false;
      await user.click(screen.getByRole('button', { name: /retry/i }));

      // Page 2 succeeds and displays page 2 content
      expect(await screen.findByText('Retry Page Item 940')).toBeInTheDocument();
      expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    });

    it('displays beyond-cap notice and disables Next at page 11 (cap 100, page size 10)', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 150 }, (_, i) => ({
        id: 1000 - i,
        title: `Deep Cap Item ${1000 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          const actualLimit = Math.min(limit, 100);
          return {
            body: items.slice(0, actualLimit),
            headers: { 'X-Total-Count': '150' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Page 1 of 15')).toBeInTheDocument();

      // Navigate to page 11
      for (let p = 1; p <= 10; p++) {
        const nextBtn = screen.getByRole('button', { name: /next/i });
        expect(nextBtn).toBeEnabled();
        await user.click(nextBtn);
      }

      // Now at Page 11 of 15
      expect(await screen.findByText('Page 11 of 15')).toBeInTheDocument();

      // Beyond-cap notice must appear
      expect(screen.getByText(/exceeds source limit cap/i)).toBeInTheDocument();

      // Next button must be disabled
      expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();

      // Previous button is enabled
      expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled();

      // Does not show misleading empty page
      expect(screen.queryByText(/no public complaints published yet/i)).not.toBeInTheDocument();
    });

    it('disables Previous on page 1 and disables Next on the last page', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 15 }, (_, i) => ({
        id: 850 - i,
        title: `Nav Item ${850 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: items.slice(0, limit),
            headers: { 'X-Total-Count': '15' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');

      expect(await screen.findByText('Page 1 of 2')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
      expect(screen.getByRole('button', { name: /next/i })).toBeEnabled();

      await user.click(screen.getByRole('button', { name: /next/i }));

      expect(await screen.findByText('Page 2 of 2')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled();
      expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
    });

    it('returns to page 1 when changing department on page 3', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 30 }, (_, i) => ({
        id: 1100 - i,
        title: `Item Alpha ${1100 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: items.slice(0, limit),
            headers: { 'X-Total-Count': '30' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

      // Navigate to page 3
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();

      // Change department
      await user.selectOptions(screen.getByLabelText(/^department$/i, { selector: 'select' }), '2');

      // Resets to Page 1
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    });

    it('returns to page 1 when changing status on page 3', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 30 }, (_, i) => ({
        id: 1200 - i,
        title: `Item Beta ${1200 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: items.slice(0, limit),
            headers: { 'X-Total-Count': '30' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

      // Navigate to page 3
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();

      // Change status
      await user.selectOptions(screen.getByLabelText(/^status$/i, { selector: 'select' }), 'submitted');

      // Resets to Page 1
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    });

    it('returns to page 1 when changing scope on page 3', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 30 }, (_, i) => ({
        id: 1300 - i,
        title: `Item Gamma ${1300 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: items.slice(0, limit),
            headers: { 'X-Total-Count': '30' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

      // Navigate to page 3
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();

      // Change scope
      await user.click(screen.getByRole('radio', { name: /my wing/i }));

      // Resets to Page 1
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    });

    it('returns to page 1 when changing hostel on page 3 (staff/admin)', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 30 }, (_, i) => ({
        id: 1400 - i,
        title: `Item Delta ${1400 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin' }) }),
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: items.slice(0, limit),
            headers: { 'X-Total-Count': '30' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

      // Navigate to page 3
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();

      // Change hostel
      const hostelSelect = screen.getByLabelText(/^hostel$/i, { selector: 'select' });
      await user.selectOptions(hostelSelect, '1');

      // Resets to Page 1
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    });

    it('returns to page 1 when clicking clear all filters on page 3', async () => {
      const user = userEvent.setup();
      const items = Array.from({ length: 30 }, (_, i) => ({
        id: 1500 - i,
        title: `Item Epsilon ${1500 - i}`,
        department_id: 2,
        department_name: 'IT Services',
        status: 'submitted',
        created_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        updated_at: new Date(2026, 9, 28, 12, 0, 0 - i).toISOString(),
        reopen_count: 0,
      }));

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': (req) => {
          const limit = Number(req.url.searchParams.get('limit') || 10);
          return {
            body: items.slice(0, limit),
            headers: { 'X-Total-Count': '30' },
          };
        },
        'GET /api/v1/feeds/departments/3': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
        'GET /api/v1/feeds/hostel': () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      });

      renderAt('/feed');
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

      // Set a filter first so Clear all filters is active
      await user.selectOptions(screen.getByLabelText(/^status$/i, { selector: 'select' }), 'submitted');

      // Navigate to page 3
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: /next/i }));
      expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();

      // Click Clear all filters
      const clearButtons = screen.getAllByRole('button', { name: /clear all filters/i });
      await user.click(clearButtons[0]);

      // Resets to Page 1
      expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    });

    it('shows notice on residence_not_verified from hostel feed while department items still render in All Departments', async () => {
      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({
          body: [
            {
              id: 1601,
              title: 'Rendered IT Complaint 1601',
              department_id: 2,
              department_name: 'IT Services',
              status: 'submitted',
              created_at: '2026-10-25T10:00:00Z',
              updated_at: '2026-10-25T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/departments/3': () => ({ body: [] }),
        'GET /api/v1/feeds/hostel': () => ({
          status: 403,
          body: { detail: { code: 'residence_not_verified', message: 'Verified residence required.' } },
        }),
      });

      renderAt('/feed');

      // Department complaint is still rendered
      expect(await screen.findByText('Rendered IT Complaint 1601')).toBeInTheDocument();

      // Notice alert is rendered
      expect(screen.getByText('Hostel complaints require a verified student residence.')).toBeInTheDocument();
    });

    it('shows notice on 401 from hostel feed while department items still render in All Departments', async () => {
      const spy = vi.spyOn(feedsApi, 'getHostelFeedApi').mockRejectedValueOnce(
        new ApiClientError(401, 'Unauthorized')
      );

      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({
          body: [
            {
              id: 1602,
              title: 'Rendered IT Complaint 1602',
              department_id: 2,
              department_name: 'IT Services',
              status: 'submitted',
              created_at: '2026-10-25T10:00:00Z',
              updated_at: '2026-10-25T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/departments/3': () => ({ body: [] }),
      });

      try {
        renderAt('/feed');

        // Department complaint is still rendered
        expect(await screen.findByText('Rendered IT Complaint 1602')).toBeInTheDocument();

        // Notice alert is rendered
        expect(screen.getByText('Authentication required to view hostel complaints.')).toBeInTheDocument();
      } finally {
        spy.mockRestore();
      }
    });

    it('shows notice on 403 from hostel feed while department items still render in All Departments', async () => {
      mockApi({
        ...baseHandlers,
        'GET /api/v1/feeds/departments/2': () => ({
          body: [
            {
              id: 1603,
              title: 'Rendered IT Complaint 1603',
              department_id: 2,
              department_name: 'IT Services',
              status: 'submitted',
              created_at: '2026-10-25T10:00:00Z',
              updated_at: '2026-10-25T10:00:00Z',
              reopen_count: 0,
            },
          ],
        }),
        'GET /api/v1/feeds/departments/3': () => ({ body: [] }),
        'GET /api/v1/feeds/hostel': () => ({
          status: 403,
          body: { detail: 'Forbidden for non-hostel staff' },
        }),
      });

      renderAt('/feed');

      // Department complaint is still rendered
      expect(await screen.findByText('Rendered IT Complaint 1603')).toBeInTheDocument();

      // Notice alert is rendered
      expect(screen.getByText('Hostel complaints are restricted for your account.')).toBeInTheDocument();
    });
  });
});
