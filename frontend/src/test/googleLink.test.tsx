import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import { makeToken, makeUser, mockApi } from './mockApi';
import { GOOGLE_LINK_MESSAGE_SUCCESS, GOOGLE_LINK_MESSAGE_ERROR } from '../context/AuthContext';

function renderAt(path: string) {
  window.history.replaceState(null, '', path);
  return render(<App />);
}

function dispatchPopupMessage(popup: unknown, data: unknown, origin = 'http://localhost:8000') {
  const ev = new MessageEvent('message', {
    origin,
    data,
  });
  Object.defineProperty(ev, 'source', { value: popup });
  window.dispatchEvent(ev);
}

describe('Login page centering', () => {
  it('applies auth-layout--centered on the login page', async () => {
    mockApi({});
    const { container } = renderAt('/login');
    const layout = container.querySelector('.auth-layout');
    expect(layout).toHaveClass('auth-layout--centered');
  });

  it('applies auth-layout--centered on the registration page', async () => {
    mockApi({});
    const { container } = renderAt('/register');
    const layout = container.querySelector('.auth-layout');
    expect(layout).toHaveClass('auth-layout--centered');
  });
});

describe('Google login account collision friendly message', () => {
  it('shows friendly message when Google sign-in fails due to existing email account', async () => {
    const user = userEvent.setup();
    mockApi({
      'POST /api/v1/auth/google/start': () => ({
        body: {
          authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?mock=1',
          state: 'test-state',
          ticket: 'test-ticket',
        },
      }),
    });

    const popupMock = {
      closed: false,
      focus: vi.fn(),
      close: vi.fn(),
      location: { href: '' },
    };
    vi.spyOn(window, 'open').mockReturnValue(popupMock as unknown as Window);

    renderAt('/login');

    const googleBtn = screen.getByRole('button', { name: /sign in with google/i });
    await user.click(googleBtn);

    // Simulate callback posting collision error message to window
    dispatchPopupMessage(popupMock, {
      type: 'CCMS_GOOGLE_AUTH_ERROR',
      error: 'An account already exists with this email. Sign in using your password, then connect Google from your account settings.',
    });

    expect(
      await screen.findByText(
        'An account already exists with this email. Sign in using your password, then connect Google from your account settings.'
      )
    ).toBeInTheDocument();
  });
});

describe('Profile Connected Accounts and Google account linking', () => {
  it('renders Connect Google Account button when unlinked', async () => {
    setStoredToken(makeToken());
    mockApi({
      'GET /api/v1/users/me': () => ({
        body: makeUser({ google_linked: false }),
      }),
    });

    renderAt('/profile');

    expect(await screen.findByRole('heading', { name: /connected accounts/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /connect google account/i })).toBeInTheDocument();
    expect(screen.queryByText(/^connected$/i)).not.toBeInTheDocument();
  });

  it('renders Connected status badge when already linked', async () => {
    setStoredToken(makeToken());
    mockApi({
      'GET /api/v1/users/me': () => ({
        body: makeUser({ google_linked: true, email: '202401001@dau.ac.in' }),
      }),
    });

    renderAt('/profile');

    expect(await screen.findByRole('heading', { name: /connected accounts/i })).toBeInTheDocument();
    expect(screen.getByText(/connected \(202401001@dau\.ac\.in\)/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /connect google account/i })).not.toBeInTheDocument();
  });

  it('successfully links Google account via popup and updates UI', async () => {
    const user = userEvent.setup();
    setStoredToken(makeToken());

    const api = mockApi({
      'GET /api/v1/users/me': () => ({
        body: makeUser({ google_linked: false, email: '202401001@dau.ac.in' }),
      }),
      'POST /api/v1/auth/google/link/start': () => ({
        body: {
          authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?mock=link',
          state: 'link-state',
          ticket: 'link-ticket',
        },
      }),
      'POST /api/v1/auth/google/link/exchange': () => ({
        body: {
          message: 'Google account linked successfully',
          user: makeUser({ google_linked: true, email: '202401001@dau.ac.in' }),
        },
      }),
    });

    const popupMock = {
      closed: false,
      focus: vi.fn(),
      close: vi.fn(),
      location: { href: '' },
    };
    vi.spyOn(window, 'open').mockReturnValue(popupMock as unknown as Window);

    renderAt('/profile');

    const connectBtn = await screen.findByRole('button', { name: /connect google account/i });
    await user.click(connectBtn);

    // Verify link start was requested
    expect(api.callsTo('POST /api/v1/auth/google/link/start')).toHaveLength(1);

    // Simulate popup posting success message back to opener
    dispatchPopupMessage(popupMock, {
      type: GOOGLE_LINK_MESSAGE_SUCCESS,
      ticket: 'handoff-ticket-123',
    });

    // Should exchange ticket
    await waitFor(() => {
      expect(api.callsTo('POST /api/v1/auth/google/link/exchange')).toHaveLength(1);
    });

    // Should show success alert
    expect(
      await screen.findByText(
        'Google account connected successfully. You can now sign in using either Google or your password.'
      )
    ).toBeInTheDocument();

    // Button should now be replaced by connected badge
    expect(screen.queryByRole('button', { name: /connect google account/i })).not.toBeInTheDocument();
    expect(screen.getByText(/^connected$/i)).toBeInTheDocument();
  });

  it('displays error alert if linking fails or is rejected', async () => {
    const user = userEvent.setup();
    setStoredToken(makeToken());

    mockApi({
      'GET /api/v1/users/me': () => ({
        body: makeUser({ google_linked: false, email: '202401001@dau.ac.in' }),
      }),
      'POST /api/v1/auth/google/link/start': () => ({
        body: {
          authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?mock=link',
          state: 'link-state',
          ticket: 'link-ticket',
        },
      }),
    });

    const popupMock = {
      closed: false,
      focus: vi.fn(),
      close: vi.fn(),
      location: { href: '' },
    };
    vi.spyOn(window, 'open').mockReturnValue(popupMock as unknown as Window);

    renderAt('/profile');

    const connectBtn = await screen.findByRole('button', { name: /connect google account/i });
    await user.click(connectBtn);

    // Simulate popup posting error message back to opener
    dispatchPopupMessage(popupMock, {
      type: GOOGLE_LINK_MESSAGE_ERROR,
      error: 'The Google account email does not match your CCMS university email.',
    });

    expect(
      await screen.findByText('The Google account email does not match your CCMS university email.')
    ).toBeInTheDocument();
  });
});
