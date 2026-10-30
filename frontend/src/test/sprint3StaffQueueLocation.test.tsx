import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import type { UserSafeResponse } from '../types';
import {
  DEPARTMENTS,
  HOSTEL_LOCATIONS,
  makeToken,
  makeUser,
  mockApi,
  type MockRequest,
} from './mockApi';

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

function complaint(id: number, location: Partial<Record<'hostel' | 'wing' | 'floor', string>> = {}) {
  return {
    id,
    title: `Maintenance issue ${id}`,
    description_preview: 'The corridor lights are not functioning.',
    department_id: 1,
    department_name: 'Hostel',
    status: 'submitted',
    created_at: '2026-10-20T09:00:00Z',
    updated_at: '2026-10-20T09:00:00Z',
    resolved_at: null,
    floor_id: location.floor ? 102 : null,
    hostel: location.hostel ?? null,
    wing: location.wing ?? null,
    floor: location.floor ?? null,
  };
}

const located = complaint(31, {
  hostel: 'Hostel A',
  wing: 'East Wing',
  floor: 'Second Floor',
});
const unlocated = complaint(32);

function setup(
  user: UserSafeResponse,
  complaints: (req: MockRequest) => { body: unknown; headers: Record<string, string> } = () => ({
    body: [located, unlocated],
    headers: { 'X-Total-Count': '2' },
  }),
) {
  const api = mockApi({
    'GET /api/v1/users/me': () => ({ body: user }),
    'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
    'GET /api/v1/locations/hostels': () => ({ body: HOSTEL_LOCATIONS }),
    'GET /api/v1/staff/complaints': complaints,
    'GET /api/v1/staff/residences': () => ({
      body: [],
      headers: { 'X-Total-Count': '0' },
    }),
  });

  setStoredToken(makeToken());
  window.history.replaceState(null, '', '/staff');
  render(<App />);

  return api;
}

function lastQueueCall(api: ReturnType<typeof mockApi>) {
  const calls = api.callsTo('GET /api/v1/staff/complaints');
  return calls[calls.length - 1];
}

describe('Sprint 3 staff queue hostel filter and location', () => {
  it('lists hostels in the dropdown, sends hostel_id and resets to page one', async () => {
    const api = setup(hostelStaff, (req) => {
      const offset = Number(req.url.searchParams.get('offset') ?? 0);
      return {
        body: Array.from({ length: 20 }, (_, index) => complaint(offset + index + 1)),
        headers: { 'X-Total-Count': '45' },
      };
    });
    const user = userEvent.setup();

    const select = await screen.findByLabelText('Filter by hostel');
    await within(select).findByRole('option', { name: 'Hostel B' });
    expect(
      within(select).getAllByRole('option').map((option) => option.textContent),
    ).toEqual(['All hostels', 'Hostel A', 'Hostel B']);

    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();

    await user.selectOptions(select, 'Hostel B');

    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    await waitFor(() => {
      const call = lastQueueCall(api);
      expect(call.url.searchParams.get('hostel_id')).toBe('2');
      expect(call.url.searchParams.get('offset')).toBe('0');
    });
  });

  it('sends no hostel_id for "All hostels"', async () => {
    const api = setup(hostelStaff);
    const user = userEvent.setup();

    const select = await screen.findByLabelText('Filter by hostel');
    await within(select).findByRole('option', { name: 'Hostel A' });
    expect(api.callsTo('GET /api/v1/staff/complaints')[0].url.searchParams.has('hostel_id')).toBe(false);

    await user.selectOptions(select, 'Hostel A');
    await waitFor(() => {
      expect(lastQueueCall(api).url.searchParams.get('hostel_id')).toBe('1');
    });

    await user.selectOptions(select, 'All hostels');
    await waitFor(() => {
      expect(lastQueueCall(api).url.searchParams.has('hostel_id')).toBe(false);
    });
  });

  it('shows each complaint location, or a dash when there is none', async () => {
    setup(hostelStaff);

    const withLocation = await screen.findByRole('button', { name: /#31/ });
    expect(within(withLocation).getByText('Location:').parentElement).toHaveTextContent(
      'Location: Hostel A, East Wing, Second Floor',
    );

    const withoutLocation = screen.getByRole('button', { name: /#32/ });
    expect(within(withoutLocation).getByText('Location:').parentElement).toHaveTextContent(
      'Location: —',
    );
  });

  it('shows non-Hostel staff no hostel filter or location and never loads hostels', async () => {
    const api = setup(itStaff);

    expect(await screen.findByText('IT Services')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /#31/ })).toBeInTheDocument();

    expect(screen.queryByLabelText('Filter by hostel')).not.toBeInTheDocument();
    expect(screen.queryByText('Location:')).not.toBeInTheDocument();
    expect(api.callsTo('GET /api/v1/locations/hostels')).toHaveLength(0);
    expect(
      api.callsTo('GET /api/v1/staff/complaints').every(
        (call) => !call.url.searchParams.has('hostel_id'),
      ),
    ).toBe(true);
  });
});
