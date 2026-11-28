/**
 * Sprint 5 S5-06: complaint comments UI (frontend/src/api/comments.ts and
 * components/ComplaintComments.tsx), on the student detail page and the staff
 * detail panel. The backend (S5-05) is stubbed with fetch mocks that follow
 * the plan's contract: oldest first, limit/offset, X-Total-Count.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import { ComplaintComments } from '../components/ComplaintComments';
import { COMMENT_MAX_LENGTH, type CommentOut } from '../api/comments';
import { setStoredToken } from '../api/client';
import { DEPARTMENTS, makeStaffScope, makeToken, makeUser, mockApi } from './mockApi';

const STUDENT_URL = '/api/v1/complaints/12/comments';
const STAFF_URL = '/api/v1/staff/complaints/12/comments';

function comment(overrides: Partial<CommentOut> & { id: number }): CommentOut {
  return {
    body: `Comment ${overrides.id}`,
    created_at: `2026-11-1${overrides.id}T10:00:00Z`,
    author_role: 'student',
    author_name: 'Aarav Patel',
    is_mine: true,
    ...overrides,
  };
}

const fromStudent = (id: number, body: string) => comment({ id, body });
const fromStaff = (id: number, body: string) =>
  comment({ id, body, author_role: 'staff', author_name: 'Meera Shah', is_mine: false });

/** Text of every rendered comment as "Label: body", in display order. */
function renderedThread(): string[] {
  return within(screen.getByRole('list', { name: /comments/i }))
    .getAllByRole('listitem')
    .map((item) => {
      const label = item.querySelector('.comment__author')?.textContent;
      const body = item.querySelector('.comment__body')?.textContent;
      return `${label}: ${body}`;
    });
}

describe('ComplaintComments: loading', () => {
  it('loads the thread oldest first with You / Staff labels', async () => {
    const api = mockApi({
      [`GET ${STUDENT_URL}`]: () => ({
        body: [
          fromStudent(1, 'The tap is still leaking.'),
          fromStaff(2, 'A plumber is booked for tomorrow.'),
          fromStudent(3, 'Thank you!'),
        ],
        headers: { 'X-Total-Count': '3' },
      }),
    });

    render(<ComplaintComments complaintId={12} audience="student" />);

    expect(screen.getByLabelText(/loading comments/i)).toBeInTheDocument();
    await screen.findByRole('list', { name: /comments/i });

    expect(renderedThread()).toEqual([
      'You: The tap is still leaking.',
      'Staff: A plumber is booked for tomorrow.',
      'You: Thank you!',
    ]);
    // Staff show their name, the viewer's own comments do not repeat it.
    expect(screen.getByText('Meera Shah')).toBeInTheDocument();
    expect(screen.queryByText('Aarav Patel')).not.toBeInTheDocument();

    const [request] = api.callsTo(`GET ${STUDENT_URL}`);
    expect(request.url.searchParams.get('limit')).toBe('100');
    expect(request.url.searchParams.get('offset')).toBe('0');
    expect(screen.queryByText(/no comments yet/i)).not.toBeInTheDocument();
  });

  it('keeps oldest first even if the server order differs', async () => {
    mockApi({
      [`GET ${STUDENT_URL}`]: () => ({
        body: [fromStudent(3, 'third'), fromStudent(1, 'first'), fromStaff(2, 'second')],
        headers: { 'X-Total-Count': '3' },
      }),
    });
    render(<ComplaintComments complaintId={12} audience="student" />);
    await screen.findByRole('list', { name: /comments/i });
    expect(renderedThread()).toEqual(['You: first', 'Staff: second', 'You: third']);
  });

  it('shows an empty state and still offers the composer', async () => {
    mockApi({ [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }) });
    render(<ComplaintComments complaintId={12} audience="student" />);

    expect(await screen.findByText(/no comments yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: /comments/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/add a comment/i)).toBeEnabled();
  });

  it('shows an error with Retry when loading fails, then recovers', async () => {
    let fail = true;
    mockApi({
      [`GET ${STUDENT_URL}`]: () =>
        fail
          ? { status: 500, body: { detail: 'boom' } }
          : { body: [fromStaff(1, 'Back online.')], headers: { 'X-Total-Count': '1' } },
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);

    expect(await screen.findByText(/couldn't load comments/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/add a comment/i)).not.toBeInTheDocument();

    fail = false;
    await user.click(screen.getByRole('button', { name: /retry/i }));
    await screen.findByText('Back online.');
  });

  it('loads further pages on demand using offset and X-Total-Count', async () => {
    const api = mockApi({
      [`GET ${STUDENT_URL}`]: (req) =>
        req.url.searchParams.get('offset') === '0'
          ? { body: [fromStudent(1, 'one'), fromStaff(2, 'two')], headers: { 'X-Total-Count': '3' } }
          : { body: [fromStudent(3, 'three')], headers: { 'X-Total-Count': '3' } },
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);

    await screen.findByRole('list', { name: /comments/i });
    expect(renderedThread()).toHaveLength(2);

    await user.click(screen.getByRole('button', { name: /load more comments/i }));
    await waitFor(() => expect(renderedThread()).toHaveLength(3));

    expect(renderedThread()[2]).toBe('You: three');
    expect(api.callsTo(`GET ${STUDENT_URL}`)[1].url.searchParams.get('offset')).toBe('2');
    expect(screen.queryByRole('button', { name: /load more comments/i })).not.toBeInTheDocument();
  });
});

describe('ComplaintComments: posting', () => {
  it('appends the new comment, sends the stripped text and clears the box', async () => {
    const api = mockApi({
      [`GET ${STUDENT_URL}`]: () => ({
        body: [fromStaff(1, 'Please share the room number.')],
        headers: { 'X-Total-Count': '1' },
      }),
      [`POST ${STUDENT_URL}`]: (req) => ({
        status: 201,
        body: comment({ id: 2, body: (req.body as { body: string }).body, created_at: '2026-11-19T12:00:00Z' }),
      }),
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);
    await screen.findByRole('list', { name: /comments/i });

    await user.type(screen.getByLabelText(/add a comment/i), '   Room 204, second floor.  ');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    await waitFor(() =>
      expect(renderedThread()).toEqual([
        'Staff: Please share the room number.',
        'You: Room 204, second floor.',
      ]),
    );
    expect(api.callsTo(`POST ${STUDENT_URL}`)[0].body).toEqual({ body: 'Room 204, second floor.' });
    expect(screen.getByLabelText(/add a comment/i)).toHaveValue('');
    expect(screen.getByText(`0/${COMMENT_MAX_LENGTH}`)).toBeInTheDocument();
    // The reply is appended locally, not by re-fetching the whole thread.
    expect(api.callsTo(`GET ${STUDENT_URL}`)).toHaveLength(1);
  });

  it('replaces the empty state with the first comment', async () => {
    mockApi({
      [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      [`POST ${STUDENT_URL}`]: () => ({ status: 201, body: fromStudent(1, 'First!') }),
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);
    await screen.findByText(/no comments yet/i);

    await user.type(screen.getByLabelText(/add a comment/i), 'First!');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    await waitFor(() => expect(renderedThread()).toEqual(['You: First!']));
    expect(screen.queryByText(/no comments yet/i)).not.toBeInTheDocument();
  });

  it('disables the textarea and button while sending, then re-enables them', async () => {
    let finish: (res: Response) => void = () => {};
    const gate = new Promise<Response>((resolve) => (finish = resolve));
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = (init?.method ?? 'GET').toUpperCase();
      if (method === 'POST') return gate;
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'content-type': 'application/json', 'X-Total-Count': '0' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);
    const box = await screen.findByLabelText(/add a comment/i);

    await user.type(box, 'Please hurry');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    await waitFor(() => expect(box).toBeDisabled());
    expect(screen.getByRole('button', { name: /sending/i })).toBeDisabled();
    expect(box).toHaveValue('Please hurry'); // text stays visible while sending

    finish(
      new Response(JSON.stringify(fromStudent(1, 'Please hurry')), {
        status: 201,
        headers: { 'content-type': 'application/json' },
      }),
    );

    await waitFor(() => expect(box).toBeEnabled());
    expect(box).toHaveValue('');
    expect(box).toHaveFocus(); // focus returns so they can keep typing
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });

  it('keeps the typed text and shows the error when posting fails, then allows a retry', async () => {
    let failing = true;
    const api = mockApi({
      [`GET ${STUDENT_URL}`]: () => ({ body: [fromStaff(1, 'Hello')], headers: { 'X-Total-Count': '1' } }),
      [`POST ${STUDENT_URL}`]: () =>
        failing
          ? { status: 500, body: { detail: 'Server exploded' } }
          : { status: 201, body: fromStudent(2, 'My careful message') },
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);
    await screen.findByRole('list', { name: /comments/i });

    const box = screen.getByLabelText(/add a comment/i);
    await user.type(box, 'My careful message');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/comment not sent/i);
    expect(box).toHaveValue('My careful message');
    expect(box).toBeEnabled();
    expect(screen.getByRole('button', { name: /post comment/i })).toBeEnabled();
    expect(renderedThread()).toEqual(['Staff: Hello']); // nothing was appended

    failing = false;
    await user.click(screen.getByRole('button', { name: /post comment/i }));
    await waitFor(() => expect(renderedThread()).toEqual(['Staff: Hello', 'You: My careful message']));
    expect(box).toHaveValue('');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(api.callsTo(`POST ${STUDENT_URL}`)).toHaveLength(2);
  });

  it('shows the server message for a rejected body and keeps the text', async () => {
    mockApi({
      [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      [`POST ${STUDENT_URL}`]: () => ({
        status: 422,
        body: { detail: [{ loc: ['body', 'body'], msg: 'Comment must be 1-1000 characters.', type: 'value_error' }] },
      }),
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);
    const box = await screen.findByLabelText(/add a comment/i);

    await user.type(box, 'x');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    expect(await screen.findByText(/must be 1-1000 characters/i)).toBeInTheDocument();
    expect(box).toHaveValue('x');
  });
});

describe('ComplaintComments: composer limits', () => {
  it('counts characters against the 1000 limit and enforces it on the textarea', async () => {
    mockApi({ [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }) });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);

    const box = await screen.findByLabelText(/add a comment/i);
    expect(screen.getByText('0/1000')).toBeInTheDocument();
    expect(box).toHaveAttribute('maxlength', '1000');

    await user.type(box, 'hello');
    expect(screen.getByText('5/1000')).toBeInTheDocument();
  });

  it('cannot send an empty or whitespace-only comment', async () => {
    const api = mockApi({ [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }) });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);

    const button = await screen.findByRole('button', { name: /post comment/i });
    expect(button).toBeDisabled();

    await user.type(screen.getByLabelText(/add a comment/i), '    ');
    expect(button).toBeDisabled();
    expect(api.callsTo(`POST ${STUDENT_URL}`)).toHaveLength(0);
  });

  it('accepts exactly 1000 characters', async () => {
    mockApi({
      [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
      [`POST ${STUDENT_URL}`]: (req) => ({
        status: 201,
        body: fromStudent(1, (req.body as { body: string }).body),
      }),
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);

    const box = await screen.findByLabelText(/add a comment/i);
    await user.click(box);
    await user.paste('a'.repeat(1000));
    expect(screen.getByText('1000/1000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /post comment/i })).toBeEnabled();
  });
});

describe('ComplaintComments: 404 handling', () => {
  it('shows an "unavailable" message instead of crashing when the thread is 404', async () => {
    mockApi({ [`GET ${STUDENT_URL}`]: () => ({ status: 404, body: { detail: 'Complaint not found.' } }) });
    render(<ComplaintComments complaintId={12} audience="student" />);

    expect(await screen.findByText(/comments aren't available for this complaint/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/add a comment/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    // The heading stays so the page layout does not jump.
    expect(screen.getByRole('heading', { name: 'Comments' })).toBeInTheDocument();
  });

  it('handles a 404 on post (access lost mid-session) without losing the page', async () => {
    mockApi({
      [`GET ${STUDENT_URL}`]: () => ({ body: [fromStaff(1, 'Hi')], headers: { 'X-Total-Count': '1' } }),
      [`POST ${STUDENT_URL}`]: () => ({ status: 404, body: { detail: 'Complaint not found.' } }),
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="student" />);
    await screen.findByRole('list', { name: /comments/i });

    await user.type(screen.getByLabelText(/add a comment/i), 'Anyone there?');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    expect(await screen.findByText(/comments aren't available for this complaint/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/add a comment/i)).not.toBeInTheDocument();
  });
});

describe('ComplaintComments: staff audience', () => {
  it('uses the staff routes and labels the student as "Student"', async () => {
    const api = mockApi({
      [`GET ${STAFF_URL}`]: () => ({
        body: [
          comment({ id: 1, body: 'Still not fixed', author_role: 'student', author_name: 'Aarav Patel', is_mine: false }),
          comment({ id: 2, body: 'On it', author_role: 'staff', author_name: 'Hostel Staff', is_mine: true }),
          comment({ id: 3, body: 'Colleague note', author_role: 'staff', author_name: 'Other Staff', is_mine: false }),
        ],
        headers: { 'X-Total-Count': '3' },
      }),
      [`POST ${STAFF_URL}`]: (req) => ({
        status: 201,
        body: comment({ id: 4, body: (req.body as { body: string }).body, author_role: 'staff', is_mine: true }),
      }),
    });
    const user = userEvent.setup();
    render(<ComplaintComments complaintId={12} audience="staff" headingLevel={3} />);
    await screen.findByRole('list', { name: /comments/i });

    expect(renderedThread()).toEqual(['Student: Still not fixed', 'You: On it', 'Staff: Colleague note']);
    expect(screen.getByRole('heading', { level: 3, name: 'Comments' })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/add a comment/i), 'Fixed today');
    await user.click(screen.getByRole('button', { name: /post comment/i }));
    await waitFor(() => expect(renderedThread()).toHaveLength(4));

    expect(api.callsTo(`GET ${STUDENT_URL}`)).toHaveLength(0);
    expect(api.callsTo(`POST ${STAFF_URL}`)).toHaveLength(1);
  });
});

describe('ComplaintComments: switching complaints', () => {
  it('drops the draft and the old thread when the complaint changes', async () => {
    mockApi({
      'GET /api/v1/complaints/12/comments': () => ({ body: [fromStaff(1, 'Thread twelve')], headers: { 'X-Total-Count': '1' } }),
      'GET /api/v1/complaints/13/comments': () => ({ body: [fromStaff(1, 'Thread thirteen')], headers: { 'X-Total-Count': '1' } }),
    });
    const user = userEvent.setup();
    const { rerender } = render(<ComplaintComments complaintId={12} audience="student" />);
    await screen.findByText('Thread twelve');
    await user.type(screen.getByLabelText(/add a comment/i), 'draft for twelve');

    rerender(<ComplaintComments complaintId={13} audience="student" />);

    await screen.findByText('Thread thirteen');
    expect(screen.queryByText('Thread twelve')).not.toBeInTheDocument();
    expect(screen.getByLabelText(/add a comment/i)).toHaveValue('');
  });
});

// ------------------------------------------------------------------ mounted on the real pages

const complaintBody = {
  id: 12,
  title: 'Leaking tap in room 204',
  description: 'The tap has been leaking for three days.',
  department_id: 1,
  department_name: 'Hostel',
  created_by_id: 1,
  status: 'in_progress',
  is_public: false,
  reopen_count: 0,
  created_at: '2026-11-10T09:00:00Z',
  updated_at: '2026-11-11T09:00:00Z',
  resolved_at: null,
};

describe('ComplaintComments: on the student ComplaintDetailPage', () => {
  it('shows the thread under the status history', async () => {
    const api = mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/complaints/12': () => ({ body: complaintBody }),
      'GET /api/v1/complaints/12/history': () => ({ body: [] }),
      [`GET ${STUDENT_URL}`]: () => ({
        body: [fromStaff(1, 'We will fix it today.')],
        headers: { 'X-Total-Count': '1' },
      }),
    });
    setStoredToken(makeToken());
    window.history.replaceState(null, '', '/complaints/12');
    render(<App />);

    expect(await screen.findByText('We will fix it today.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Comments' })).toBeInTheDocument();
    expect(screen.getByLabelText(/add a comment/i)).toBeEnabled();
    expect(api.callsTo(`GET ${STUDENT_URL}`)).toHaveLength(1);
  });

  it('stays open on a rejected complaint so the student can ask why', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/complaints/12': () => ({ body: { ...complaintBody, status: 'rejected' } }),
      'GET /api/v1/complaints/12/history': () => ({ body: [] }),
      [`GET ${STUDENT_URL}`]: () => ({ body: [], headers: { 'X-Total-Count': '0' } }),
    });
    setStoredToken(makeToken());
    window.history.replaceState(null, '', '/complaints/12');
    render(<App />);

    expect(await screen.findByLabelText(/add a comment/i)).toBeEnabled();
  });

  it('does not break the page when the comments request fails', async () => {
    mockApi({
      'GET /api/v1/users/me': () => ({ body: makeUser() }),
      'GET /api/v1/complaints/12': () => ({ body: complaintBody }),
      'GET /api/v1/complaints/12/history': () => ({ body: [] }),
      [`GET ${STUDENT_URL}`]: () => ({ status: 404, body: { detail: 'Complaint not found.' } }),
    });
    setStoredToken(makeToken());
    window.history.replaceState(null, '', '/complaints/12');
    render(<App />);

    expect(await screen.findByText(/comments aren't available/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Leaking tap in room 204' })).toBeInTheDocument();
  });
});

describe('ComplaintComments: on the staff detail view', () => {
  const staff = makeUser({ id: 5, role: 'staff', name: 'Hostel Staff', department_id: 1 });
  const queueItem = {
    id: 12,
    title: 'Leaking tap in room 204',
    description_preview: 'The tap has been leaking',
    department_id: 1,
    department_name: 'Hostel',
    status: 'in_progress',
    created_at: '2026-11-10T09:00:00Z',
    updated_at: '2026-11-11T09:00:00Z',
    resolved_at: null,
    floor_id: null,
    hostel: null,
    wing: null,
    floor: null,
  };

  it('loads the staff thread when a complaint is opened, and posts to the staff route', async () => {
    const api = mockApi({
      'GET /api/v1/users/me': () => ({ body: staff }),
      'GET /api/v1/staff/me/hostels': () => ({ body: makeStaffScope(1, [1]) }),
      'GET /api/v1/departments': () => ({ body: DEPARTMENTS }),
      'GET /api/v1/staff/complaints': () => ({ body: [queueItem], headers: { 'X-Total-Count': '1' } }),
      'GET /api/v1/staff/complaints/12': () => ({ body: { ...complaintBody, hostel: null, wing: null, floor: null } }),
      'GET /api/v1/complaints/12/history': () => ({ body: [] }),
      [`GET ${STAFF_URL}`]: () => ({
        body: [comment({ id: 1, body: 'Is anyone coming?', is_mine: false })],
        headers: { 'X-Total-Count': '1' },
      }),
      [`POST ${STAFF_URL}`]: (req) => ({
        status: 201,
        body: comment({ id: 2, body: (req.body as { body: string }).body, author_role: 'staff', is_mine: true }),
      }),
    });
    setStoredToken(makeToken());
    window.history.replaceState(null, '', '/staff');
    render(<App />);
    const user = userEvent.setup();

    // Nothing is requested until a complaint is opened.
    await user.click(await screen.findByRole('button', { name: /#12/ }));

    expect(await screen.findByText('Is anyone coming?')).toBeInTheDocument();
    expect(screen.getByText('Student')).toBeInTheDocument();

    await user.type(screen.getByLabelText(/add a comment/i), 'Plumber arrives at 4pm.');
    await user.click(screen.getByRole('button', { name: /post comment/i }));

    await waitFor(() => expect(screen.getByText('Plumber arrives at 4pm.')).toBeInTheDocument());
    expect(api.callsTo(`POST ${STAFF_URL}`)[0].body).toEqual({ body: 'Plumber arrives at 4pm.' });
    expect(api.callsTo(`GET ${STUDENT_URL}`)).toHaveLength(0);
  });
});
