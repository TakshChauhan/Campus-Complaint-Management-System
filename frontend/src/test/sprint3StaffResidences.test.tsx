import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import type { StaffResidenceItem } from '../api/staff';
import type { UserSafeResponse } from '../types';
import { DEPARTMENTS, makeToken, makeUser, mockApi, type MockRequest } from './mockApi';

const hostelStaff = makeUser({
  role: 'staff',
  name: 'Hostel Staff',
  department_id: 1,
});

const itStaff = makeUser({
  role: 'staff',
  name: 'IT Staff',
  department_id: 2,
});

function residence(id: number, overrides: Partial<StaffResidenceItem> = {}): StaffResidenceItem {
  return {
    id,
    student_id: 100 + id,
    student_name: `Student ${id}`,
    student_email: `20240100${id}@dau.ac.in`,
    floor_id: 100 + id,
    hostel: 'Hostel A',
    wing: 'East Wing',
    floor: 'First Floor',
    status: 'pending',
    remark: null,
    submitted_at: '2026-10-20T09:00:00Z',
    decided_at: null,
    ...overrides,
  };
}

type Handler = (req: MockRequest) => {
  status?: number;
  body?: unknown;
  headers?: Record<string, string>;
};

function setup(user: UserSafeResponse, extraHandlers: Record<string, Handler> = {}) {
  let pending: StaffResidenceItem[] = [
    residence(1, { student_name: 'Riya Shah', student_email: '202401011@dau.ac.in' }),
    residence(2, {
      student_name: 'Kabir Mehta',
      student_email: '202401022@dau.ac.in',
      hostel: 'Hostel B',
      wing: 'North Wing',
      floor: 'Ground Floor',
    }),
  ];

  const api = mockApi({
    'GET /api/v1/users/me': () => ({ body: user }),
    'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
    'GET /api/v1/staff/complaints': () => ({
      body: [],
      headers: { 'X-Total-Count': '0' },
    }),
    'GET /api/v1/staff/residences': () => ({
      body: pending,
      headers: { 'X-Total-Count': String(pending.length) },
    }),
    'POST /api/v1/staff/residences/1/decision': () => {
      pending = pending.filter((item) => item.id !== 1);
      return { body: residence(1, { status: 'verified' }) };
    },
    'POST /api/v1/staff/residences/2/decision': () => {
      pending = pending.filter((item) => item.id !== 2);
      return { body: residence(2, { status: 'rejected' }) };
    },
    ...extraHandlers,
  });

  setStoredToken(makeToken());
  window.history.replaceState(null, '', '/staff');
  render(<App />);

  return api;
}

async function findRow(id: number) {
  const heading = await screen.findByRole('heading', {
    name: new RegExp(`Residence declaration #${id}$`),
  });
  return heading.closest('article') as HTMLElement;
}

describe('Sprint 3 staff residence verification queue', () => {
  it('shows the pending residence queue to Hostel staff', async () => {
    const api = setup(hostelStaff);

    const row1 = await findRow(1);
    expect(within(row1).getByText(/Riya Shah/)).toBeInTheDocument();
    expect(within(row1).getByText('202401011@dau.ac.in')).toBeInTheDocument();
    expect(within(row1).getByText('Hostel A')).toBeInTheDocument();
    expect(within(row1).getByText('East Wing')).toBeInTheDocument();
    expect(within(row1).getByText('First Floor')).toBeInTheDocument();

    const row2 = await findRow(2);
    expect(within(row2).getByText(/Kabir Mehta/)).toBeInTheDocument();
    expect(within(row2).getByText('202401022@dau.ac.in')).toBeInTheDocument();
    expect(within(row2).getByText('Hostel B')).toBeInTheDocument();
    expect(within(row2).getByText('North Wing')).toBeInTheDocument();
    expect(within(row2).getByText('Ground Floor')).toBeInTheDocument();

    expect(
      api.callsTo('GET /api/v1/staff/residences')[0].url.searchParams.get('status'),
    ).toBe('pending');
  });

  it('hides the residence queue from non-Hostel staff and never requests it', async () => {
    const api = setup(itStaff);

    expect(await screen.findByText(/no complaints found/i)).toBeInTheDocument();
    expect(await screen.findByText('IT Services')).toBeInTheDocument();

    expect(
      screen.queryByRole('heading', { name: /residence verification queue/i }),
    ).not.toBeInTheDocument();
    expect(api.callsTo('GET /api/v1/staff/residences')).toHaveLength(0);
  });

  it('approves a residence and refreshes the queue', async () => {
    const api = setup(hostelStaff);
    const user = userEvent.setup();

    const row1 = await findRow(1);
    await user.click(within(row1).getByRole('button', { name: /approve residence/i }));

    await waitFor(() => {
      expect(api.callsTo('POST /api/v1/staff/residences/1/decision')).toHaveLength(1);
    });
    expect(api.callsTo('POST /api/v1/staff/residences/1/decision')[0].body).toEqual({
      decision: 'approve',
    });

    expect(
      await screen.findByText(/Residence declaration for Riya Shah approved/i),
    ).toBeInTheDocument();
    expect(api.callsTo('GET /api/v1/staff/residences').length).toBeGreaterThanOrEqual(2);
    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { name: /Residence declaration #1$/ }),
      ).not.toBeInTheDocument();
    });
    expect(await findRow(2)).toBeInTheDocument();
  });

  it('blocks rejection without a remark and sends the remark when provided', async () => {
    const api = setup(hostelStaff);
    const user = userEvent.setup();

    const row2 = await findRow(2);
    await user.click(within(row2).getByRole('button', { name: /reject residence/i }));

    expect(
      await screen.findByText(/a remark is required when rejecting/i),
    ).toBeInTheDocument();
    expect(api.callsTo('POST /api/v1/staff/residences/2/decision')).toHaveLength(0);

    await user.type(within(row2).getByRole('textbox'), 'Room allotment does not match.');
    await user.click(within(row2).getByRole('button', { name: /reject residence/i }));

    await waitFor(() => {
      expect(api.callsTo('POST /api/v1/staff/residences/2/decision')).toHaveLength(1);
    });
    expect(api.callsTo('POST /api/v1/staff/residences/2/decision')[0].body).toEqual({
      decision: 'reject',
      remark: 'Room allotment does not match.',
    });
  });

  it('keeps remarks separate for each residence row', async () => {
    setup(hostelStaff);
    const user = userEvent.setup();

    const row1 = await findRow(1);
    const row2 = await findRow(2);

    await user.type(within(row1).getByRole('textbox'), 'Checked with warden.');

    expect(within(row1).getByRole('textbox')).toHaveValue('Checked with warden.');
    expect(within(row2).getByRole('textbox')).toHaveValue('');
  });

  it('shows an already-decided message on 409', async () => {
    setup(hostelStaff, {
      'POST /api/v1/staff/residences/1/decision': () => ({
        status: 409,
        body: { detail: 'Residence already decided' },
      }),
    });
    const user = userEvent.setup();

    const row1 = await findRow(1);
    await user.click(within(row1).getByRole('button', { name: /approve residence/i }));

    expect(await screen.findByText(/already been decided/i)).toBeInTheDocument();
  });
});
