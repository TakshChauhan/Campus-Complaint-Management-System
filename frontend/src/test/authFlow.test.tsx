import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { getStoredToken, setStoredToken } from '../api/client';
import { DEPARTMENTS, makeToken, makeUser, mockApi } from './mockApi';

function renderAt(path: string) {
  window.history.replaceState(null, '', path);
  return render(<App />);
}

const recentEmpty = () => ({ body: [], headers: { 'X-Total-Count': '0' } });

describe('registration', () => {
  it('goes to sign-in with a success message, prefilled email and no session', async () => {
    const api = mockApi({
      'POST /api/v1/auth/register': (req) => ({
        status: 201,
        body: makeUser({ email: (req.body as { email: string }).email, name: 'New Student' }),
      }),
    });
    const user = userEvent.setup();
    renderAt('/register');

    await user.type(screen.getByLabelText(/full name/i), 'New Student');
    await user.type(screen.getByLabelText(/university email/i), '202499999@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'CampusPass123');
    await user.type(screen.getByLabelText(/confirm password/i), 'CampusPass123');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByText('Account created! Check your inbox for the verification link. After verifying your email, you can sign in.')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByLabelText(/university email/i)).toHaveValue('202499999@dau.ac.in');

    // No automatic login: no token, no login call, no profile call, no complaint page.
    expect(getStoredToken()).toBeNull();
    expect(api.callsTo('POST /api/v1/auth/login')).toHaveLength(0);
    expect(api.callsTo('GET /api/v1/users/me')).toHaveLength(0);
    expect(screen.queryByRole('heading', { name: /raise a complaint/i })).not.toBeInTheDocument();
  });

  it('validates fields before calling the API', async () => {
    const api = mockApi({});
    const user = userEvent.setup();
    renderAt('/register');
    await user.type(screen.getByLabelText(/university email/i), 'someone@gmail.com');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'short');
    await user.type(screen.getByLabelText(/confirm password/i), 'different');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(screen.getByText(/enter your full name/i)).toBeInTheDocument();
    expect(screen.getByText(/use your university email ending in/i)).toBeInTheDocument();
    expect(screen.getByText(/use at least 8 characters/i)).toBeInTheDocument();
    expect(screen.getByText(/passwords don't match/i)).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it('shows a duplicate-account message from the server', async () => {
    mockApi({ 'POST /api/v1/auth/register': () => ({ status: 409, body: { detail: 'exists' } }) });
    const user = userEvent.setup();
    renderAt('/register');
    await user.type(screen.getByLabelText(/full name/i), 'New Student');
    await user.type(screen.getByLabelText(/university email/i), '202499999@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'CampusPass123');
    await user.type(screen.getByLabelText(/confirm password/i), 'CampusPass123');
    await user.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe('/register');
  });
});

describe('sign-in', () => {
  it('opens the student dashboard, not the complaint form', async () => {
    const token = makeToken();
    mockApi({
      'POST /api/v1/auth/login': () => ({ body: { access_token: token, token_type: 'bearer', expires_in: 3600, user: makeUser() } }),
      'GET /api/v1/complaints/mine': recentEmpty,
    });
    const user = userEvent.setup();
    renderAt('/login');
    await user.type(screen.getByLabelText(/university email/i), '202401001@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'CampusPass123');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    expect(await screen.findByRole('heading', { name: /welcome back, aarav/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/dashboard');
    expect(getStoredToken()).toBe(token);
    expect(screen.queryByRole('heading', { name: /raise a complaint/i })).not.toBeInTheDocument();
    expect(await screen.findByText("You haven't raised a complaint yet")).toBeInTheDocument();
  });

  it('shows a clear message for wrong credentials and keeps the user on the page', async () => {
    mockApi({ 'POST /api/v1/auth/login': () => ({ status: 401, body: { detail: 'Invalid email or password.' } }) });
    const user = userEvent.setup();
    renderAt('/login');
    await user.type(screen.getByLabelText(/university email/i), '202401001@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'wrong-password');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));
    expect(await screen.findByText('Incorrect email or password.')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(screen.queryByText(/session has expired/i)).not.toBeInTheDocument();
  });

  it('shows the server message for an inactive account', async () => {
    mockApi({
      'POST /api/v1/auth/login': () => ({ status: 403, body: { detail: 'Account is inactive. Please contact system administrator.' } }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await user.type(screen.getByLabelText(/university email/i), '202401001@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'CampusPass123');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));
    expect(await screen.findByText(/account is inactive/i)).toBeInTheDocument();
  });

  it('toggles password visibility', async () => {
    mockApi({});
    const user = userEvent.setup();
    renderAt('/login');
    const input = screen.getByLabelText(/^password/i, { selector: 'input' });
    expect(input).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: /show password/i }));
    expect(input).toHaveAttribute('type', 'text');
  });

  it('routes staff and admins to their own overview', async () => {
    mockApi({
      'POST /api/v1/auth/login': () => ({
        body: { access_token: makeToken(), token_type: 'bearer', expires_in: 3600, user: makeUser({ role: 'staff', name: 'Staff John' }) },
      }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
    });
    const user = userEvent.setup();
    renderAt('/login');
    await user.type(screen.getByLabelText(/university email/i), 'staff@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'CampusPass123');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));
    expect(await screen.findByRole('heading', { name: /hello, staff/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/staff');
  });
});

describe('protected routes and sessions', () => {
  it('sends anonymous visitors to sign-in and back to the page they asked for', async () => {
    mockApi({
      'POST /api/v1/auth/login': () => ({ body: { access_token: makeToken(), token_type: 'bearer', expires_in: 3600, user: makeUser() } }),
      'GET /api/v1/complaints/mine': recentEmpty,
    });
    const user = userEvent.setup();
    renderAt('/complaints');
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');

    await user.type(screen.getByLabelText(/university email/i), '202401001@dau.ac.in');
    await user.type(screen.getByLabelText(/^password/i, { selector: 'input' }), 'CampusPass123');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));
    expect(await screen.findByRole('heading', { name: 'My complaints' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/complaints');
  });

  it('restores a valid session on refresh without flashing the sign-in page', async () => {
    setStoredToken(makeToken());
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/complaints/mine': recentEmpty,
    });
    renderAt('/dashboard');
    expect(screen.getByText(/checking your session/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: /welcome back/i })).toBeInTheDocument();
  });

  it('treats an expired stored token as signed out', async () => {
    setStoredToken(makeToken(-60));
    const api = mockApi({});
    renderAt('/dashboard');
    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(getStoredToken()).toBeNull();
    expect(api.callsTo('GET /api/v1/users/me')).toHaveLength(0);
  });

  it('ends the session when the API rejects the token', async () => {
    setStoredToken(makeToken());
    mockApi({ 'GET /api/v1/users/me': () => ({ status: 401, body: { detail: 'Could not validate credentials or token expired' } }) });
    renderAt('/dashboard');
    expect(await screen.findByText(/session has expired/i)).toBeInTheDocument();
    expect(getStoredToken()).toBeNull();
  });

  it('blocks students from admin and staff pages', async () => {
    setStoredToken(makeToken());
    mockApi({ 'GET /api/v1/users/me': () => ({ body: makeUser() }) });
    renderAt('/admin');
    expect(await screen.findByText(/isn't available for your account/i)).toBeInTheDocument();
    expect(screen.queryByText(/service status/i)).not.toBeInTheDocument();
  });

  it('blocks staff from student complaint pages', async () => {
    setStoredToken(makeToken());
    mockApi({ 'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'staff' }) }) });
    renderAt('/complaints/new');
    expect(await screen.findByText(/isn't available for your account/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/complaint title/i)).not.toBeInTheDocument();
  });

  it('signs out, clears the token and returns to sign-in', async () => {
    setStoredToken(makeToken());
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/complaints/mine': recentEmpty,
    });
    const user = userEvent.setup();
    renderAt('/dashboard');
    await screen.findByRole('heading', { name: /welcome back/i });
    await user.click(screen.getAllByRole('button', { name: /sign out/i })[0]);
    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(getStoredToken()).toBeNull();
    expect(screen.queryByText(/session has expired/i)).not.toBeInTheDocument();
  });

  it('redirects a signed-in user away from the sign-in page', async () => {
    setStoredToken(makeToken());
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/complaints/mine': recentEmpty,
    });
    renderAt('/login');
    expect(await screen.findByRole('heading', { name: /welcome back/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/dashboard');
  });
});
