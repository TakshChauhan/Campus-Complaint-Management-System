/**
 * Sprint 4 S4-14 / S4-15: hostel-scoped staff screens.
 *
 * Hostel staff see only their assigned hostels (GET /staff/me/hostels,
 * API_CONTRACT.md 7.14) in the queue's hostel filter; staff with no hostels see
 * a clear empty state; S4-04's 404 for out-of-scope items is explained.
 */
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import type { StaffResidenceItem } from '../api/staff';
import type { HostelNode, UserSafeResponse } from '../types';
import {
  DEPARTMENTS,
  makeStaffScope,
  makeToken,
  makeUser,
  mockApi,
  type MockRequest,
} from './mockApi';

const hostelStaff = makeUser({ id: 7, role: 'staff', name: 'Meera Joshi', department_id: 1 });
const itStaff = makeUser({ id: 8, role: 'staff', name: 'Ravi Iyer', department_id: 2 });

/** A third hostel, so a two-hostel staff member is not simply "all hostels". */
const HOSTEL_C: HostelNode = { id: 3, code: 'HC', name: 'Hostel C', wings: [] };

type Reply = { status?: number; body?: unknown; headers?: Record<string, string> };
type Handler = (req: MockRequest) => Reply;

function complaint(id: number, hostel: string | null) {
  return {
    id,
    title: `Maintenance issue ${id}`,
    description_preview: 'The corridor lights are not functioning.',
    department_id: 1,
    department_name: 'Hostel',
    status: 'submitted',
    created_at: '2026-11-01T09:00:00Z',
    updated_at: '2026-11-01T09:00:00Z',
    resolved_at: null,
    floor_id: hostel ? 101 : null,
    hostel,
    wing: hostel ? 'East Wing' : null,
    floor: hostel ? 'First Floor' : null,
  };
}

function detail(id: number, hostel: string) {
  return {
    ...complaint(id, hostel),
    description: 'The corridor lights are not functioning on the first floor.',
    is_public: false,
    reopen_count: 0,
  };
}

function residence(id: number, hostel: string): StaffResidenceItem {
  return {
    id,
    student_id: 100 + id,
    student_name: `Student ${id}`,
    student_email: `20240100${id}@dau.ac.in`,
    floor_id: 101,
    hostel,
    wing: 'East Wing',
    floor: 'First Floor',
    status: 'pending',
    remark: null,
    submitted_at: '2026-11-01T09:00:00Z',
    decided_at: null,
  };
}

function setup(
  user: UserSafeResponse,
  scope: Handler,
  {
    complaints = [complaint(41, 'Hostel A')],
    residences = [] as StaffResidenceItem[],
    extra = {} as Record<string, Handler>,
    /** Holds the scope response back until this promise settles. */
    scopeGate = undefined as Promise<void> | undefined,
  } = {},
) {
  const api = mockApi({
    'GET /api/v1/users/me': () => ({ body: user }),
    'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
    'GET /api/v1/staff/me/hostels': scope,
    'GET /api/v1/staff/complaints': () => ({
      body: complaints,
      headers: { 'X-Total-Count': String(complaints.length) },
    }),
    'GET /api/v1/staff/residences': () => ({
      body: residences,
      headers: { 'X-Total-Count': String(residences.length) },
    }),
    ...extra,
  });

  if (scopeGate) {
    const respond = api.fetchMock.getMockImplementation()!;
    api.fetchMock.mockImplementation(async (input, init) => {
      if (String(input).includes('/staff/me/hostels')) await scopeGate;
      return respond(input, init);
    });
  }

  setStoredToken(makeToken());
  window.history.replaceState(null, '', '/staff');
  render(<App />);
  return api;
}

const assigned = (...ids: number[]): Handler => () => ({
  body: makeStaffScope(1, ids, [HOSTEL_C]),
});

function lastQueueCall(api: ReturnType<typeof mockApi>) {
  const calls = api.callsTo('GET /api/v1/staff/complaints');
  return calls[calls.length - 1];
}

function optionNames(select: HTMLElement) {
  return within(select).getAllByRole('option').map((option) => option.textContent);
}

async function findAccountPanel() {
  const heading = await screen.findByRole('heading', { name: 'Your staff account' });
  return heading.closest('section') as HTMLElement;
}

describe('S4-14 hostel-scoped staff screens', () => {
  describe('staff with one hostel', () => {
    it('shows the hostel on the account panel and header, and only it in the filter', async () => {
      const api = setup(hostelStaff, assigned(2));

      const panel = await findAccountPanel();
      expect(await within(panel).findByText('Assigned hostels:')).toBeInTheDocument();
      expect(within(panel).getByText('Assigned hostels:').parentElement).toHaveTextContent(
        'Assigned hostels: Hostel B',
      );
      expect(
        screen.getByText('Complaints and residence declarations for Hostel B.'),
      ).toBeInTheDocument();

      const select = await screen.findByLabelText('Filter by hostel');
      expect(optionNames(select)).toEqual(['All my hostels', 'Hostel B']);

      // The full campus hostel list is never used for the filter any more.
      expect(api.callsTo('GET /api/v1/locations/hostels')).toHaveLength(0);
    });

    it('sends the hostel_id of the chosen hostel', async () => {
      const api = setup(hostelStaff, assigned(2));
      const user = userEvent.setup();

      const select = await screen.findByLabelText('Filter by hostel');
      await screen.findByRole('button', { name: /#41/ });
      expect(lastQueueCall(api).url.searchParams.has('hostel_id')).toBe(false);

      await user.selectOptions(select, 'Hostel B');
      await waitFor(() => {
        expect(lastQueueCall(api).url.searchParams.get('hostel_id')).toBe('2');
      });
    });

    it('loads the residence queue, which the backend limits to the hostel', async () => {
      const api = setup(hostelStaff, assigned(2), { residences: [residence(5, 'Hostel B')] });

      const heading = await screen.findByRole('heading', { name: /Residence declaration #5$/ });
      expect(within(heading.closest('article') as HTMLElement).getByText('Hostel B')).toBeInTheDocument();
      expect(api.callsTo('GET /api/v1/staff/residences')).toHaveLength(1);
    });

    it('waits for the scope before loading the complaint queue', async () => {
      let releaseScope: () => void = () => {};
      const scopeGate = new Promise<void>((resolve) => {
        releaseScope = resolve;
      });
      const api = setup(hostelStaff, assigned(2), { scopeGate });

      await screen.findByRole('heading', { name: 'Your staff account' });
      await waitFor(() => expect(api.callsTo('GET /api/v1/departments')).toHaveLength(1));
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(api.callsTo('GET /api/v1/staff/complaints')).toHaveLength(0);

      releaseScope();
      expect(await screen.findByRole('button', { name: /#41/ })).toBeInTheDocument();
      expect(api.callsTo('GET /api/v1/staff/complaints')).toHaveLength(1);
    });
  });

  describe('staff with two hostels', () => {
    it('lists exactly the two assigned hostels and none of the others', async () => {
      setup(hostelStaff, assigned(3, 1));

      const select = await screen.findByLabelText('Filter by hostel');
      // Sorted by name; Hostel B exists on campus but is not assigned.
      expect(optionNames(select)).toEqual(['All my hostels', 'Hostel A', 'Hostel C']);
      expect(within(select).queryByRole('option', { name: 'Hostel B' })).not.toBeInTheDocument();

      const panel = await findAccountPanel();
      expect(within(panel).getByText('Assigned hostels:').parentElement).toHaveTextContent(
        'Assigned hostels: Hostel A, Hostel C',
      );
      expect(
        screen.getByText('Complaints and residence declarations for Hostel A and Hostel C.'),
      ).toBeInTheDocument();
    });

    it('switches between the two hostels and back to all of them', async () => {
      const api = setup(hostelStaff, assigned(1, 3), {
        complaints: [complaint(41, 'Hostel A'), complaint(42, 'Hostel C')],
      });
      const user = userEvent.setup();

      const select = await screen.findByLabelText('Filter by hostel');
      expect(await screen.findByRole('button', { name: /#42/ })).toBeInTheDocument();

      await user.selectOptions(select, 'Hostel C');
      await waitFor(() => expect(lastQueueCall(api).url.searchParams.get('hostel_id')).toBe('3'));

      await user.selectOptions(select, 'Hostel A');
      await waitFor(() => expect(lastQueueCall(api).url.searchParams.get('hostel_id')).toBe('1'));

      await user.selectOptions(select, 'All my hostels');
      await waitFor(() => expect(lastQueueCall(api).url.searchParams.has('hostel_id')).toBe(false));
      expect(lastQueueCall(api).url.searchParams.get('offset')).toBe('0');
    });
  });

  describe('staff with no hostels', () => {
    it('shows a clear empty state and requests neither queue', async () => {
      const api = setup(hostelStaff, assigned());

      expect(await screen.findByText('No hostels assigned to you yet')).toBeInTheDocument();
      expect(screen.getByText(/Ask an administrator to assign your hostels/)).toBeInTheDocument();
      expect(
        screen.getByText('Residence declarations appear here once a hostel is assigned to you.'),
      ).toBeInTheDocument();

      const panel = await findAccountPanel();
      expect(within(panel).getByText('Assigned hostels:').parentElement).toHaveTextContent(
        'Assigned hostels: None assigned',
      );

      expect(screen.queryByLabelText('Filter by hostel')).not.toBeInTheDocument();
      expect(screen.queryByText(/No complaints found/)).not.toBeInTheDocument();
      expect(screen.getByLabelText('Filter by status')).toBeDisabled();
      expect(screen.getByLabelText('Filter residence requests by status')).toBeDisabled();
      for (const button of screen.getAllByRole('button', { name: 'Refresh' })) {
        expect(button).toBeDisabled();
      }

      expect(api.callsTo('GET /api/v1/staff/complaints')).toHaveLength(0);
      expect(api.callsTo('GET /api/v1/staff/residences')).toHaveLength(0);
    });
  });

  describe('out-of-scope items (S4-04 returns 404)', () => {
    it('explains a 404 when opening a complaint', async () => {
      setup(hostelStaff, assigned(1), {
        extra: {
          'GET /api/v1/staff/complaints/41': () => ({ status: 404, body: { detail: 'Complaint not found' } }),
        },
      });
      const user = userEvent.setup();

      await user.click(await screen.findByRole('button', { name: /#41/ }));

      expect(
        await screen.findByText(/This complaint is not in your assigned hostels, or it no longer exists/),
      ).toBeInTheDocument();
    });

    it('explains a 404 on a status update and refreshes the queue', async () => {
      const api = setup(hostelStaff, assigned(1), {
        extra: {
          'GET /api/v1/staff/complaints/41': () => ({ body: detail(41, 'Hostel A') }),
          'GET /api/v1/complaints/41/history': () => ({ body: [] }),
          'PATCH /api/v1/staff/complaints/41/status': () => ({
            status: 404,
            body: { detail: 'Complaint not found' },
          }),
        },
      });
      const user = userEvent.setup();

      await user.click(await screen.findByRole('button', { name: /#41/ }));
      await user.type(await screen.findByLabelText('Remark (required)'), 'Electrician assigned.');
      const queueCallsBefore = api.callsTo('GET /api/v1/staff/complaints').length;
      await user.click(screen.getByRole('button', { name: 'Save status update' }));

      expect(
        await screen.findByText(/This complaint is not in your assigned hostels, or it no longer exists/),
      ).toBeInTheDocument();
      await waitFor(() =>
        expect(api.callsTo('GET /api/v1/staff/complaints').length).toBeGreaterThan(queueCallsBefore),
      );
    });

    it('explains a 404 on a residence decision and reloads the residence queue', async () => {
      const api = setup(hostelStaff, assigned(1), {
        residences: [residence(9, 'Hostel A')],
        extra: {
          'POST /api/v1/staff/residences/9/decision': () => ({
            status: 404,
            body: { detail: 'Residence not found' },
          }),
        },
      });
      const user = userEvent.setup();

      await user.click(await screen.findByRole('button', { name: 'Approve residence' }));

      expect(
        await screen.findByText(/not in your assigned hostels any more/),
      ).toBeInTheDocument();
      await waitFor(() =>
        expect(api.callsTo('GET /api/v1/staff/residences').length).toBeGreaterThanOrEqual(2),
      );
    });
  });

  describe('scope loading failure', () => {
    it('warns, keeps the queue usable without a hostel filter, and recovers on retry', async () => {
      let fail = true;
      const api = setup(hostelStaff, () =>
        fail
          ? { status: 500, body: { detail: 'Server error' } }
          : { body: makeStaffScope(1, [1]) },
      );
      const user = userEvent.setup();

      expect(await screen.findByText("Couldn't load your assigned hostels")).toBeInTheDocument();
      // The backend still scopes the queue, so it loads without a hostel filter.
      expect(await screen.findByRole('button', { name: /#41/ })).toBeInTheDocument();
      expect(screen.queryByLabelText('Filter by hostel')).not.toBeInTheDocument();
      expect(lastQueueCall(api).url.searchParams.has('hostel_id')).toBe(false);

      fail = false;
      await user.click(screen.getByRole('button', { name: 'Try again' }));

      const select = await screen.findByLabelText('Filter by hostel');
      expect(optionNames(select)).toEqual(['All my hostels', 'Hostel A']);
      expect(screen.queryByText("Couldn't load your assigned hostels")).not.toBeInTheDocument();
    });
  });

  describe('non-Hostel staff', () => {
    it('are unchanged: no hostel filter, no assigned hostels, no residence queue', async () => {
      const api = setup(itStaff, () => ({ body: makeStaffScope(2, []) }), {
        complaints: [{ ...complaint(51, null), department_id: 2, department_name: 'IT Services' }],
      });

      expect(await screen.findByRole('button', { name: /#51/ })).toBeInTheDocument();
      expect(screen.queryByLabelText('Filter by hostel')).not.toBeInTheDocument();
      expect(screen.queryByText('Assigned hostels:')).not.toBeInTheDocument();
      expect(screen.queryByText('No hostels assigned to you yet')).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Residence verification queue' })).not.toBeInTheDocument();
      expect(api.callsTo('GET /api/v1/staff/residences')).toHaveLength(0);
    });
  });
});
