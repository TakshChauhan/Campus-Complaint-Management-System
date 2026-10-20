import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { mockApi } from './mockApi';

function visit(path: string) {
  window.history.replaceState(null, '', path);
  return render(<App />);
}

describe('verification links', () => {
  it('submits the opaque token once and opens a sign-in link on success', async () => {
    const mock = mockApi({
      'POST /api/v1/auth/verify-email': (req) => {
        expect(req.body).toEqual({ token: 'one-use-token' });
        return { body: { message: 'Your email address has been verified successfully.', email: 'new@dau.ac.in' } };
      },
    });
    visit('/verify-email?token=one-use-token');
    expect(await screen.findByText(/verified successfully/i)).toBeInTheDocument();
    expect(mock.callsTo('POST /api/v1/auth/verify-email')).toHaveLength(1);
    expect(window.location.search).toBe('');
    expect(screen.getByRole('button', { name: /continue to sign in/i })).toBeInTheDocument();
  });

  it('requires a token and does not call the API if it is missing', async () => {
    const mock = mockApi({});
    visit('/verify-email');
    expect(await screen.findByText(/does not contain a verification token/i)).toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });

  it('allows resending a verification email and never treats the response as a session', async () => {
    const mock = mockApi({
      'POST /api/v1/auth/resend-verification': (req) => {
        expect(req.body).toEqual({ email: 'student@dau.ac.in' });
        return { body: { message: 'If an account exists and requires verification, a new link has been sent.' } };
      },
    });
    const user = userEvent.setup();
    visit('/resend-verification');
    await user.type(screen.getByLabelText(/university email/i), 'student@dau.ac.in');
    await user.click(screen.getByRole('button', { name: /send verification email/i }));
    await waitFor(() => expect(mock.callsTo('POST /api/v1/auth/resend-verification')).toHaveLength(1));
    expect(await screen.findByText(/a new link has been sent/i)).toBeInTheDocument();
    expect(window.location.pathname).toBe('/resend-verification');
  });
});
