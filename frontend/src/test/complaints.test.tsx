import { describe, expect, it } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import { DEPARTMENTS, makeToken, makeUser, mockApi } from './mockApi';

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

const base = {
  'GET /api/v1/users/me': () => ({ body: makeUser() }),
  'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
};

const listItem = (id: number, title: string, dept = 'IT Services') => ({
  id,
  title,
  description_preview: `${title} description preview`,
  department_id: 2,
  department_name: dept,
  status: 'submitted',
  created_at: '2026-10-12T09:30:00Z',
});

async function fillValidComplaint(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByLabelText(/complaint title/i), 'Wi-Fi down in Lab 3');
  await user.type(screen.getByLabelText(/description/i, { selector: 'textarea' }), 'The Wi-Fi drops every few minutes in Lab 3 since yesterday.');
  await user.selectOptions(await screen.findByLabelText(/^department/i, { selector: 'select' }), '2');
}

describe('raise complaint', () => {
  it('shows inline validation and does not submit an incomplete form', async () => {
    const api = mockApi(base);
    const user = userEvent.setup();
    renderAt('/complaints/new');
    await screen.findByLabelText(/^department/i, { selector: 'select' });
    await user.click(screen.getByRole('button', { name: /submit complaint/i }));
    expect(screen.getByText(/title of at least 3 characters/i)).toBeInTheDocument();
    expect(screen.getByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(screen.getByText(/choose the department/i)).toBeInTheDocument();
    expect(api.callsTo('POST /api/v1/complaints')).toHaveLength(0);
  });

  it('shows a character counter', async () => {
    mockApi(base);
    const user = userEvent.setup();
    renderAt('/complaints/new');
    await user.type(await screen.findByLabelText(/complaint title/i), 'Fan');
    expect(screen.getByText('3/120')).toBeInTheDocument();
  });

  it('submits once, shows the backend reference and offers next steps', async () => {
    let resolveCreate: () => void = () => {};
    const gate = new Promise<void>((r) => (resolveCreate = r));
    const api = mockApi({
      ...base,
      'POST /api/v1/complaints': (req) => ({
        status: 201,
        body: {
          id: 4821,
          ...(req.body as object),
          department_name: 'IT Services',
          created_by_id: 1,
          status: 'submitted',
          created_at: '2026-10-14T05:00:00Z',
        },
      }),
    });
    // Slow the POST down so a double click lands while it is in flight.
    const originalFetch = api.fetchMock.getMockImplementation()!;
    api.fetchMock.mockImplementation(async (input, init) => {
      if (init?.method === 'POST') await gate;
      return originalFetch(input, init);
    });

    const user = userEvent.setup();
    renderAt('/complaints/new');
    await fillValidComplaint(user);
    const submit = screen.getByRole('button', { name: /submit complaint/i });
    await user.click(submit);
    await user.click(submit);
    resolveCreate();

    expect(await screen.findByRole('heading', { name: /complaint submitted/i })).toBeInTheDocument();
    expect(api.callsTo('POST /api/v1/complaints')).toHaveLength(1);
    expect(screen.getByText('CMP-4821')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy reference cmp-4821/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /view my complaints/i })).toHaveAttribute('href', '/complaints');
    expect(screen.getByRole('link', { name: /return to dashboard/i })).toHaveAttribute('href', '/dashboard');

    // "Raise another" opens an empty form; it is never reopened automatically.
    await user.click(screen.getByRole('button', { name: /raise another complaint/i }));
    expect(screen.getByLabelText(/complaint title/i)).toHaveValue('');
  });

  it('keeps the text when submission fails', async () => {
    mockApi({ ...base, 'POST /api/v1/complaints': () => ({ status: 500, body: { detail: 'Internal server error. Please try again later.' } }) });
    const user = userEvent.setup();
    renderAt('/complaints/new');
    await fillValidComplaint(user);
    await user.click(screen.getByRole('button', { name: /submit complaint/i }));
    expect(await screen.findByText(/wasn't submitted/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/complaint title/i)).toHaveValue('Wi-Fi down in Lab 3');
    expect(screen.getByRole('button', { name: /submit complaint/i })).toBeEnabled();
  });

  it('shows the keyword suggestion and applies it only when accepted', async () => {
    mockApi({
      ...base,
      'POST /api/v1/departments/suggest': () => ({
        body: {
          status: 'provisional_advisory',
          version: 'v1.2.0-keyword',
          suggestions: [{ department_id: 2, department_name: 'IT Services', confidence_score: 0.8, rationale: 'Matched keywords relating to IT Services: wifi' }],
          disclaimer: 'advisory',
        },
      }),
    });
    const user = userEvent.setup();
    renderAt('/complaints/new');
    await user.type(await screen.findByLabelText(/complaint title/i), 'Wi-Fi down in Lab 3');
    await user.type(screen.getByLabelText(/description/i, { selector: 'textarea' }), 'The Wi-Fi drops every few minutes.');
    await user.click(screen.getByRole('button', { name: /suggest a department/i }));
    expect(await screen.findByText(/suggested department:/i)).toBeInTheDocument();
    expect(screen.queryByText(/machine learning|AI prediction/i)).not.toBeInTheDocument();
    const select = screen.getByLabelText(/^department/i, { selector: 'select' });
    expect(select).toHaveValue('');
    await user.click(screen.getByRole('button', { name: /use it services/i }));
    expect(select).toHaveValue('2');
  });

  it('explains an uncertain suggestion', async () => {
    mockApi({
      ...base,
      'POST /api/v1/departments/suggest': () => ({ body: { status: 'uncertain', version: 'v', suggestions: [], disclaimer: '' } }),
    });
    const user = userEvent.setup();
    renderAt('/complaints/new');
    await user.type(await screen.findByLabelText(/complaint title/i), 'Something odd');
    await user.type(screen.getByLabelText(/description/i, { selector: 'textarea' }), 'Hard to describe issue here.');
    await user.click(screen.getByRole('button', { name: /suggest a department/i }));
    expect(await screen.findByText(/no department keywords matched/i)).toBeInTheDocument();
  });

  it('offers retry when departments fail to load', async () => {
    let fail = true;
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/departments': () => (fail ? { status: 500, body: { detail: 'boom' } } : { body: DEPARTMENTS }),
    });
    const user = userEvent.setup();
    renderAt('/complaints/new');
    expect(await screen.findByText(/departments couldn't be loaded/i)).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByLabelText(/^department/i, { selector: 'select' })).toBeInTheDocument();
  });
});

describe('my complaints', () => {
  it('renders backend records with the real total and pages with limit/offset', async () => {
    const api = mockApi({
      ...base,
      'GET /api/v1/complaints/mine': (req) => {
        const offset = Number(req.url.searchParams.get('offset'));
        const items = offset === 0
          ? Array.from({ length: 10 }, (_, i) => listItem(30 - i, `Complaint ${30 - i}`))
          : Array.from({ length: 2 }, (_, i) => listItem(20 - i, `Complaint ${20 - i}`));
        return { body: items, headers: { 'X-Total-Count': '12' } };
      },
    });
    const user = userEvent.setup();
    renderAt('/complaints');
    expect(await screen.findByText('Showing 1–10 of 12 complaints')).toBeInTheDocument();
    expect(screen.getByText('CMP-30')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /next/i }));
    expect(await screen.findByText('Showing 11–12 of 12 complaints')).toBeInTheDocument();
    const listCalls = api.callsTo('GET /api/v1/complaints/mine');
    const last = listCalls[listCalls.length - 1];
    expect(last.url.searchParams.get('limit')).toBe('10');
    expect(last.url.searchParams.get('offset')).toBe('10');
    expect(window.location.search).toContain('page=2');
  });

  it('searches on the server, not just the visible page', async () => {
    const api = mockApi({
      ...base,
      'GET /api/v1/complaints/mine': (req) => {
        const q = req.url.searchParams.get('q');
        return q
          ? { body: [listItem(3, 'Leaking tap', 'Hostel')], headers: { 'X-Total-Count': '1' } }
          : { body: [listItem(9, 'Projector')], headers: { 'X-Total-Count': '1' } };
      },
    });
    const user = userEvent.setup();
    renderAt('/complaints');
    await screen.findByText('CMP-9');
    await user.type(screen.getByRole('searchbox'), 'leaking');
    expect(await screen.findByText('Leaking tap')).toBeInTheDocument();
    const searched = api.callsTo('GET /api/v1/complaints/mine').find((c) => c.url.searchParams.get('q') === 'leaking');
    expect(searched).toBeDefined();
    expect(searched!.url.searchParams.get('offset')).toBe('0');
  });

  it('shows an empty state for a new student', async () => {
    mockApi({ ...base, 'GET /api/v1/complaints/mine': () => ({ body: [], headers: { 'X-Total-Count': '0' } }) });
    renderAt('/complaints');
    expect(await screen.findByText('No complaints yet')).toBeInTheDocument();
  });

  it('shows an error with retry', async () => {
    let fail = true;
    mockApi({
      ...base,
      'GET /api/v1/complaints/mine': () => (fail ? { status: 503, body: { detail: 'Service unavailable' } } : { body: [listItem(1, 'Back again')], headers: { 'X-Total-Count': '1' } }),
    });
    const user = userEvent.setup();
    renderAt('/complaints');
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/service unavailable/i)).toBeInTheDocument();
    fail = false;
    await user.click(within(alert).getByRole('button', { name: /retry/i }));
    expect(await screen.findByText('Back again')).toBeInTheDocument();
  });

  it('opens a complaint detail page', async () => {
    mockApi({
      ...base,
      'GET /api/v1/complaints/7': () => ({
        body: { id: 7, title: 'Fan broken', description: 'Ceiling fan in Room 101 stopped.', department_id: 1, department_name: 'Hostel', created_by_id: 1, status: 'submitted', created_at: '2026-10-10T10:00:00Z' },
      }),
    });
    renderAt('/complaints/7');
    expect(await screen.findByRole('heading', { name: 'Fan broken' })).toBeInTheDocument();
    expect(screen.getByText('Ceiling fan in Room 101 stopped.')).toBeInTheDocument();
  });

  it('shows not found for complaints that are not yours', async () => {
    mockApi({ ...base, 'GET /api/v1/complaints/99': () => ({ status: 404, body: { detail: 'Complaint not found.' } }) });
    renderAt('/complaints/99');
    expect(await screen.findByText('CMP-99 not found')).toBeInTheDocument();
  });
});

describe('dashboard and admin data honesty', () => {
  it('shows the accurate total from the API', async () => {
    mockApi({ ...base, 'GET /api/v1/complaints/mine': () => ({ body: [listItem(5, 'Recent one')], headers: { 'X-Total-Count': '17' } }) });
    renderAt('/dashboard');
    expect(await screen.findByText('17')).toBeInTheDocument();
    expect(screen.getByText('Recent one')).toBeInTheDocument();
  });

  it('does not invent a total when the server does not send one', async () => {
    mockApi({ ...base, 'GET /api/v1/complaints/mine': () => ({ body: [listItem(5, 'Recent one')] }) });
    renderAt('/dashboard');
    expect(await screen.findByText('Not available')).toBeInTheDocument();
  });

  it('never shows healthy when the health check fails', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin', name: 'Admin Chief' }) }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /health': () => ({ status: 500, body: { detail: 'down' } }),
      'GET /health/ready': () => ({ status: 503, body: { ready: false, database: 'unavailable' } }),
    });
    renderAt('/admin');
    expect(await screen.findByText('Unreachable')).toBeInTheDocument();
    expect(await screen.findByText('Not reachable')).toBeInTheDocument();
    expect(screen.queryByText('Healthy')).not.toBeInTheDocument();
    expect(screen.queryByText(/operational/i)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Active departments (3)')).toBeInTheDocument());
  });

  it('shows healthy only from a real healthy response', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'admin' }) }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /health': () => ({ body: { status: 'healthy', project: 'CCMS', version: '1.0.0', environment: 'development', database: 'operational' } }),
      'GET /health/ready': () => ({ body: { ready: true, database: 'operational' } }),
    });
    renderAt('/admin');
    expect(await screen.findByText('Healthy')).toBeInTheDocument();
    expect(await screen.findByText('Ready')).toBeInTheDocument();
  });
});
