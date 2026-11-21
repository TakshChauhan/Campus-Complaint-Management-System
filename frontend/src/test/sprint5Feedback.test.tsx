import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { setStoredToken } from '../api/client';
import { DEPARTMENTS, makeToken, makeUser, mockApi } from './mockApi';
import { FeedbackForm } from '../components/FeedbackForm';

function renderAt(path: string) {
  setStoredToken(makeToken());
  window.history.replaceState(null, '', path);
  return render(<App />);
}

const baseUser = makeUser({ id: 1, role: 'student', name: 'Aarav Patel' });

const resolvedComplaint = {
  id: 42,
  title: 'Water cooler leaking',
  description: 'Water cooler on first floor is leaking constantly.',
  department_id: 1,
  department_name: 'Hostel',
  created_by_id: 1,
  status: 'resolved',
  created_at: '2026-11-10T10:00:00Z',
  resolved_at: '2026-11-12T14:30:00Z',
  reopen_count: 0,
};

const submittedComplaint = {
  ...resolvedComplaint,
  id: 43,
  status: 'submitted',
  resolved_at: null,
};

describe('S5-09: FeedbackForm component tests', () => {
  it('renders 5 keyboard-accessible radio buttons and comment field with 500-character limit', () => {
    render(<FeedbackForm complaintId={42} />);

    expect(screen.getByRole('heading', { name: /how was your complaint resolved/i })).toBeInTheDocument();

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(5);
    expect(radios[0]).toHaveAttribute('value', '1');
    expect(radios[4]).toHaveAttribute('value', '5');

    const commentInput = screen.getByLabelText(/comments/i, { selector: 'textarea' });
    expect(commentInput).toBeInTheDocument();
    expect(commentInput).toHaveAttribute('maxLength', '500');
    expect(screen.getByText('0/500')).toBeInTheDocument();
  });

  it('validates that a rating must be selected before submit', async () => {
    const user = userEvent.setup();
    render(<FeedbackForm complaintId={42} />);

    const submitBtn = screen.getByRole('button', { name: /submit feedback/i });
    await user.click(submitBtn);

    expect(screen.getByText('Please select a rating between 1 and 5.')).toBeInTheDocument();
  });

  it('updates character counter when typing comment', async () => {
    const user = userEvent.setup();
    render(<FeedbackForm complaintId={42} />);

    const commentInput = screen.getByLabelText(/comments/i, { selector: 'textarea' });
    await user.type(commentInput, 'Very quick resolution!');

    expect(screen.getByText('22/500')).toBeInTheDocument();
  });

  it('submits feedback and displays "You rated this 4/5"', async () => {
    const api = mockApi({
      'POST /api/v1/complaints/42/feedback': (req) => {
        const body = req.body as { rating: number; comment?: string };
        return {
          status: 201,
          body: {
            id: 101,
            complaint_id: 42,
            student_id: 1,
            rating: body.rating,
            comment: body.comment ?? null,
            created_at: '2026-11-21T12:00:00Z',
          },
        };
      },
    });

    const user = userEvent.setup();
    render(<FeedbackForm complaintId={42} />);

    // Select rating 4
    const radio4 = screen.getByRole('radio', { name: /4 star/i });
    await user.click(radio4);

    // Enter comment
    const commentInput = screen.getByLabelText(/comments/i, { selector: 'textarea' });
    await user.type(commentInput, 'Prompt and polite staff.');

    // Submit
    const submitBtn = screen.getByRole('button', { name: /submit feedback/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('You rated this 4/5')).toBeInTheDocument();
    });
    expect(screen.getByText('"Prompt and polite staff."')).toBeInTheDocument();
    expect(api.callsTo('POST /api/v1/complaints/42/feedback')).toHaveLength(1);
    expect(api.callsTo('POST /api/v1/complaints/42/feedback')[0].body).toEqual({
      rating: 4,
      comment: 'Prompt and polite staff.',
    });
  });

  it('renders "You rated this 5/5" directly if feedback already exists', () => {
    render(
      <FeedbackForm
        complaintId={42}
        initialFeedback={{
          id: 99,
          complaint_id: 42,
          student_id: 1,
          rating: 5,
          comment: 'Perfect repair',
          created_at: '2026-11-20T10:00:00Z',
        }}
      />
    );

    expect(screen.getByText('You rated this 5/5')).toBeInTheDocument();
    expect(screen.getByText('"Perfect repair"')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit feedback/i })).not.toBeInTheDocument();
  });

  it('handles 409 Conflict by refetching existing feedback and displaying "You rated this 4/5"', async () => {
    let getCalled = false;
    mockApi({
      'POST /api/v1/complaints/42/feedback': () => ({
        status: 409,
        body: { detail: 'Feedback already submitted for this complaint' },
      }),
      'GET /api/v1/complaints/42/feedback': () => {
        getCalled = true;
        return {
          status: 200,
          body: {
            id: 88,
            complaint_id: 42,
            student_id: 1,
            rating: 4,
            comment: 'Submitted from mobile app',
            created_at: '2026-11-21T11:00:00Z',
          },
        };
      },
    });

    const user = userEvent.setup();
    render(<FeedbackForm complaintId={42} />);

    const radio3 = screen.getByRole('radio', { name: /3 star/i });
    await user.click(radio3);

    const submitBtn = screen.getByRole('button', { name: /submit feedback/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('You rated this 4/5')).toBeInTheDocument();
    });
    expect(getCalled).toBe(true);
  });

  it('displays error alert when submit fails with server error', async () => {
    mockApi({
      'POST /api/v1/complaints/42/feedback': () => ({
        status: 500,
        body: { detail: 'Internal database error' },
      }),
    });

    const user = userEvent.setup();
    render(<FeedbackForm complaintId={42} />);

    const radio5 = screen.getByRole('radio', { name: /5 star/i });
    await user.click(radio5);

    const submitBtn = screen.getByRole('button', { name: /submit feedback/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Internal database error/)).toBeInTheDocument();
    });
    // Rating selection is preserved
    expect(radio5).toBeChecked();
  });
});

describe('S5-09: ComplaintDetailPage feedback integration tests', () => {
  it('does NOT show feedback form when complaint is not resolved', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: baseUser }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/complaints/43': () => ({ body: submittedComplaint }),
      'GET /api/v1/complaints/43/history': () => ({ body: [] }),
      'GET /api/v1/complaints/43/feedback': () => ({ body: null }),
    });

    renderAt('/complaints/43');

    await screen.findByRole('heading', { name: 'Water cooler leaking' });
    expect(screen.queryByRole('heading', { name: /resolution feedback/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit feedback/i })).not.toBeInTheDocument();
  });

  it('shows feedback form on resolved complaint when no feedback exists', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: baseUser }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/complaints/42': () => ({ body: resolvedComplaint }),
      'GET /api/v1/complaints/42/history': () => ({ body: [] }),
      'GET /api/v1/complaints/42/feedback': () => ({ body: null }),
    });

    renderAt('/complaints/42');

    expect(await screen.findByRole('heading', { name: /resolution feedback/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /how was your complaint resolved/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /submit feedback/i })).toBeInTheDocument();
  });

  it('shows "You rated this 4/5" when resolved complaint already has feedback', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: baseUser }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/complaints/42': () => ({ body: resolvedComplaint }),
      'GET /api/v1/complaints/42/history': () => ({ body: [] }),
      'GET /api/v1/complaints/42/feedback': () => ({
        body: {
          id: 55,
          complaint_id: 42,
          student_id: 1,
          rating: 4,
          comment: 'Resolved quickly and cleanly.',
          created_at: '2026-11-15T09:00:00Z',
        },
      }),
    });

    renderAt('/complaints/42');

    expect(await screen.findByText('You rated this 4/5')).toBeInTheDocument();
    expect(screen.getByText('"Resolved quickly and cleanly."')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit feedback/i })).not.toBeInTheDocument();
  });
});
