import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import {
  DEPARTMENTS,
  HOSTEL_LOCATIONS,
  makeToken,
  makeUser,
  mockApi,
} from './mockApi';

function visit(path: string) {
  window.history.replaceState(null, '', path);
  return render(<App />);
}

function renderAuthenticated(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

describe('S5-25: Forgot Password, Reset Password and Change Password', () => {
  describe('Forgot Password workflow', () => {
    it('submits email and displays neutral success message', async () => {
      const mock = mockApi({
        'POST /api/v1/auth/forgot-password': (req) => {
          expect(req.body).toEqual({ email: 'aarav.patel@dau.ac.in' });
          return {
            status: 202,
            body: {
              message: 'If this email address is registered, password reset instructions have been sent.',
            },
          };
        },
      });

      const user = userEvent.setup();
      visit('/forgot-password');

      expect(screen.getByRole('heading', { name: /forgot password/i })).toBeInTheDocument();
      await user.type(screen.getByLabelText(/university email/i), 'aarav.patel@dau.ac.in');
      await user.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(mock.callsTo('POST /api/v1/auth/forgot-password')).toHaveLength(1);
      });
      expect(
        await screen.findByText(/if this email address is registered, password reset instructions have been sent/i)
      ).toBeInTheDocument();
    });

    it('rejects invalid email client-side without calling API', async () => {
      const mock = mockApi({});
      const user = userEvent.setup();
      visit('/forgot-password');

      await user.type(screen.getByLabelText(/university email/i), 'not-an-email');
      await user.click(screen.getByRole('button', { name: /send reset link/i }));

      expect(await screen.findByText(/enter a valid university email address/i)).toBeInTheDocument();
      expect(mock.calls).toHaveLength(0);
    });

    it('handles rate-limit 429 error from backend', async () => {
      mockApi({
        'POST /api/v1/auth/forgot-password': () => ({
          status: 429,
          body: { detail: 'Too many password reset requests for this email address. Please try again later.' },
        }),
      });

      const user = userEvent.setup();
      visit('/forgot-password');

      await user.type(screen.getByLabelText(/university email/i), 'rate.limited@dau.ac.in');
      await user.click(screen.getByRole('button', { name: /send reset link/i }));

      expect(
        await screen.findByText(/too many password reset requests/i)
      ).toBeInTheDocument();
    });

    it('login page includes a link to forgot password', async () => {
      mockApi({});
      visit('/login');

      const forgotLink = screen.getByRole('link', { name: /reset password/i });
      expect(forgotLink).toBeInTheDocument();
      expect(forgotLink.getAttribute('href')).toBe('/forgot-password');
    });
  });

  describe('Reset Password workflow', () => {
    it('shows error state when reset token is missing', async () => {
      mockApi({});
      visit('/reset-password');

      expect(await screen.findByRole('heading', { name: /invalid reset link/i })).toBeInTheDocument();
      expect(screen.getByText(/no reset token was found in the link/i)).toBeInTheDocument();
    });

    it('resets password successfully when given valid token and matching passwords', async () => {
      const mock = mockApi({
        'POST /api/v1/auth/reset-password': (req) => {
          expect(req.body).toEqual({
            token: 'valid-reset-token-123',
            password: 'NewSecurePassword123',
          });
          return {
            status: 200,
            body: {
              message: 'Password has been successfully reset. You can now log in with your new password.',
            },
          };
        },
      });

      const user = userEvent.setup();
      visit('/reset-password?token=valid-reset-token-123');

      expect(screen.getByRole('heading', { name: /reset your password/i })).toBeInTheDocument();

      await user.type(screen.getByLabelText(/^new password/i), 'NewSecurePassword123');
      await user.type(screen.getByLabelText(/^confirm new password/i), 'NewSecurePassword123');
      await user.click(screen.getByRole('button', { name: /set new password/i }));

      await waitFor(() => {
        expect(mock.callsTo('POST /api/v1/auth/reset-password')).toHaveLength(1);
      });
      expect(
        await screen.findByText(/password has been successfully reset/i)
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in with new password/i })).toBeInTheDocument();
    });

    it('validates password mismatch client-side', async () => {
      const mock = mockApi({});
      const user = userEvent.setup();
      visit('/reset-password?token=valid-token');

      await user.type(screen.getByLabelText(/^new password/i), 'NewSecurePassword123');
      await user.type(screen.getByLabelText(/^confirm new password/i), 'DifferentPassword456');
      await user.click(screen.getByRole('button', { name: /set new password/i }));

      expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
      expect(mock.calls).toHaveLength(0);
    });

    it('handles invalid or expired token 400 error from backend', async () => {
      mockApi({
        'POST /api/v1/auth/reset-password': () => ({
          status: 400,
          body: { detail: 'Invalid or expired password reset token.' },
        }),
      });

      const user = userEvent.setup();
      visit('/reset-password?token=expired-token');

      await user.type(screen.getByLabelText(/^new password/i), 'NewSecurePassword123');
      await user.type(screen.getByLabelText(/^confirm new password/i), 'NewSecurePassword123');
      await user.click(screen.getByRole('button', { name: /set new password/i }));

      expect(
        await screen.findByText(/this reset link is invalid, expired, or has already been used/i)
      ).toBeInTheDocument();
    });
  });

  describe('Change Password workflow in ProfilePage', () => {
    const profileSetup = () => ({
      'GET /api/v1/users/me': () => ({ body: makeUser({ role: 'student' }) }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/locations/hostels': () => ({ body: HOSTEL_LOCATIONS }),
      'GET /api/v1/users/me/residence': () => ({ status: 404, body: null }),
    });

    it('changes password successfully when current and new passwords are valid', async () => {
      const mock = mockApi({
        ...profileSetup(),
        'POST /api/v1/users/me/change-password': (req) => {
          expect(req.body).toEqual({
            current_password: 'OldPassword123',
            new_password: 'NewSecurePassword456',
          });
          return {
            status: 200,
            body: { message: 'Password changed successfully.' },
          };
        },
      });

      const user = userEvent.setup();
      renderAuthenticated('/profile');

      expect(await screen.findByRole('heading', { name: /change password/i })).toBeInTheDocument();

      await user.type(screen.getByLabelText(/^current password/i), 'OldPassword123');
      await user.type(screen.getByLabelText(/^new password/i), 'NewSecurePassword456');
      await user.type(screen.getByLabelText(/^confirm new password/i), 'NewSecurePassword456');
      await user.click(screen.getByRole('button', { name: /update password/i }));

      await waitFor(() => {
        expect(mock.callsTo('POST /api/v1/users/me/change-password')).toHaveLength(1);
      });
      expect(await screen.findByText(/password changed successfully/i)).toBeInTheDocument();
    });

    it('rejects identical new password client-side', async () => {
      const mock = mockApi(profileSetup());
      const user = userEvent.setup();
      renderAuthenticated('/profile');

      expect(await screen.findByRole('heading', { name: /change password/i })).toBeInTheDocument();

      await user.type(screen.getByLabelText(/^current password/i), 'SamePassword123');
      await user.type(screen.getByLabelText(/^new password/i), 'SamePassword123');
      await user.type(screen.getByLabelText(/^confirm new password/i), 'SamePassword123');
      await user.click(screen.getByRole('button', { name: /update password/i }));

      expect(
        await screen.findByText(/new password cannot be the same as your current password/i)
      ).toBeInTheDocument();
      expect(mock.callsTo('POST /api/v1/users/me/change-password')).toHaveLength(0);
    });

    it('handles incorrect current password 400 error from backend', async () => {
      mockApi({
        ...profileSetup(),
        'POST /api/v1/users/me/change-password': () => ({
          status: 400,
          body: { detail: 'Incorrect current password.' },
        }),
      });

      const user = userEvent.setup();
      renderAuthenticated('/profile');

      expect(await screen.findByRole('heading', { name: /change password/i })).toBeInTheDocument();

      await user.type(screen.getByLabelText(/^current password/i), 'WrongCurrentPassword123');
      await user.type(screen.getByLabelText(/^new password/i), 'BrandNewPassword456');
      await user.type(screen.getByLabelText(/^confirm new password/i), 'BrandNewPassword456');
      await user.click(screen.getByRole('button', { name: /update password/i }));

      expect(await screen.findByText(/incorrect current password/i)).toBeInTheDocument();
    });
  });
});
