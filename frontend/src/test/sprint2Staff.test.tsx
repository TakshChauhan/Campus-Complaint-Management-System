import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import { DEPARTMENTS, makeToken, makeUser, mockApi } from './mockApi';

const staff = makeUser({
  role: 'staff',
  name: 'Hostel Staff',
  department_id: 1,
});

function complaint(status: string) {
  return {
    id: 23,
    title: 'Hostel lighting issue',
    description: 'The corridor lights are not functioning.',
    description_preview: 'The corridor lights are not functioning.',
    department_id: 1,
    department_name: 'Hostel',
    status,
    is_public: false,
    hostel: 'Block B',
    wing: null,
    floor: null,
    reopen_count: 0,
    created_at: '2026-10-20T09:00:00Z',
    updated_at: '2026-10-21T09:00:00Z',
    resolved_at: status === 'resolved'
      ? '2026-10-21T09:00:00Z'
      : null,
  };
}

function setup(status: string) {
  const api = mockApi({
    'GET /api/v1/users/me': () => ({ body: staff }),
    'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
    'GET /api/v1/staff/complaints': () => ({
      body: [complaint(status)],
      headers: { 'X-Total-Count': '1' },
    }),
    'GET /api/v1/staff/complaints/23': () => ({
      body: complaint(status),
    }),
    'GET /api/v1/complaints/23/history': () => ({
      body: [],
    }),
    'PATCH /api/v1/staff/complaints/23/status': () => ({
      body: complaint('in_progress'),
    }),
  });

  setStoredToken(makeToken());
  window.history.replaceState(null, '', '/staff');
  render(<App />);

  return api;
}

describe('Sprint 2 staff dashboard', () => {
  it.each([
    ['submitted', 'in_progress'],
    ['in_progress', 'resolved'],
    ['reopened', 'in_progress'],
  ])(
    'only allows %s to transition to %s',
    async (current, expected) => {
      setup(current);
      const user = userEvent.setup();

      await user.click(
        await screen.findByRole('button', { name: /#23/ })
      );

      await screen.findByRole('heading', {
        name: /#23.*Hostel lighting issue/,
      });

      const select = screen.getByLabelText('New status');
      const options = within(select).getAllByRole('option');

      expect(options).toHaveLength(1);
      expect(options[0]).toHaveValue(expected);
    }
  );

  it('does not offer staff transitions for resolved complaints', async () => {
    setup('resolved');
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole('button', { name: /#23/ })
    );

    expect(
      await screen.findByText(/reopening is handled separately/i)
    ).toBeInTheDocument();

    expect(screen.queryByLabelText('New status')).not.toBeInTheDocument();
  });

  it('sends the correct status and required remark', async () => {
    const api = setup('submitted');
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole('button', { name: /#23/ })
    );

    await screen.findByLabelText('New status');

    const save = screen.getByRole('button', {
      name: /save status update/i,
    });

    expect(save).toBeDisabled();

    await user.type(
      screen.getByLabelText(/remark \(required\)/i),
      'Staff has started investigating the issue.'
    );

    await user.click(save);

    await waitFor(() => {
      expect(
        api.callsTo('PATCH /api/v1/staff/complaints/23/status')
      ).toHaveLength(1);
    });

    expect(
      api.callsTo('PATCH /api/v1/staff/complaints/23/status')[0].body
    ).toEqual({
      status: 'in_progress',
      remark: 'Staff has started investigating the issue.',
    });

    expect(
      await screen.findByText(/status updated successfully/i)
    ).toBeInTheDocument();
  });
});

describe('Sprint 2 staff dashboard pagination', () => {
  it('loads subsequent pages and resets to page one on filter change', async () => {
    const api = mockApi({
      'GET /api/v1/users/me': () => ({ body: staff }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/staff/complaints': (req) => {
        const offset = Number(req.url.searchParams.get('offset') ?? 0);

        return {
          body: Array.from({ length: 20 }, (_, index) => ({
            ...complaint('submitted'),
            id: offset + index + 1,
            title: `Maintenance issue ${offset + index + 1}`,
          })),
          headers: { 'X-Total-Count': '45' },
        };
      },
    });

    setStoredToken(makeToken());
    window.history.replaceState(null, '', '/staff');
    render(<App />);

    const user = userEvent.setup();

    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));

    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();

    await waitFor(() => {
      expect(
        api.callsTo('GET /api/v1/staff/complaints').some(
          (call) =>
            call.url.searchParams.get('limit') === '20' &&
            call.url.searchParams.get('offset') === '20'
        )
      ).toBe(true);
    });

    await user.selectOptions(
      screen.getByLabelText('Filter by status'),
      'submitted'
    );

    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();

    await waitFor(() => {
      expect(
        api.callsTo('GET /api/v1/staff/complaints').some(
          (call) =>
            call.url.searchParams.get('status') === 'submitted' &&
            call.url.searchParams.get('offset') === '0'
        )
      ).toBe(true);
    });
  });
});

describe('Staff complaint selection race protection', () => {
  it('keeps the latest complaint visible when an older response finishes last', async () => {
    const first = {
      ...complaint('submitted'),
      id: 23,
      title: 'First complaint',
    };
    const second = {
      ...complaint('in_progress'),
      id: 24,
      title: 'Second complaint',
    };

    const api = mockApi({
      'GET /api/v1/users/me': () => ({ body: staff }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/staff/complaints': () => ({
        body: [first, second],
        headers: { 'X-Total-Count': '2' },
      }),
      'GET /api/v1/staff/complaints/23': () => ({ body: first }),
      'GET /api/v1/staff/complaints/24': () => ({ body: second }),
      'GET /api/v1/complaints/23/history': () => ({ body: [] }),
      'GET /api/v1/complaints/24/history': () => ({ body: [] }),
    });

    let releaseFirst!: () => void;
    const gate = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });

    const originalFetch = api.fetchMock.getMockImplementation()!;

    api.fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      );

      if (url.pathname === '/api/v1/staff/complaints/23') {
        await gate;
      }

      return originalFetch(input, init);
    });

    setStoredToken(makeToken());
    window.history.replaceState(null, '', '/staff');
    render(<App />);

    const user = userEvent.setup();

    await user.click(
      await screen.findByRole('button', { name: /#23/ })
    );

    await user.click(
      screen.getByRole('button', { name: /#24/ })
    );

    expect(
      await screen.findByRole('heading', {
        name: /#24.*Second complaint/,
      })
    ).toBeInTheDocument();

    releaseFirst();

    await waitFor(() => {
      expect(
        api.callsTo('GET /api/v1/staff/complaints/23')
      ).toHaveLength(1);
    });

    expect(
      screen.getByRole('heading', {
        name: /#24.*Second complaint/,
      })
    ).toBeInTheDocument();

    expect(
      screen.queryByRole('heading', {
        name: /#23.*First complaint/,
      })
    ).not.toBeInTheDocument();
  });
});
