/**
 * Complaint comments (Sprint 5, S5-06 / API contract 7.16).
 *
 * Two route families share one response shape:
 *   student (owner)  GET/POST /complaints/{id}/comments
 *   staff (in scope) GET/POST /staff/complaints/{id}/comments
 *
 * The backend returns 404 both for "no such complaint" and "not yours / out of
 * scope", so callers treat 404 as "no access" without telling the two apart.
 * Comments are append-only: there is deliberately no edit or delete here.
 */
import { apiFetch, apiRequest } from './client';

/** Server limit for a comment body, after stripping (contract 7.16). */
export const COMMENT_MAX_LENGTH = 1000;

/** Largest page the server accepts; the default is 50. */
export const COMMENT_PAGE_SIZE = 100;

export type CommentAudience = 'student' | 'staff';

/** Never carries the author's email or user id. */
export interface CommentOut {
  id: number;
  body: string;
  created_at: string;
  /** "student" or "staff"; kept as a string so a new role cannot break rendering. */
  author_role: string;
  author_name: string | null;
  /** True when the signed-in user wrote it. */
  is_mine: boolean;
}

export interface CommentPage {
  items: CommentOut[];
  /** From X-Total-Count; null when the header is missing or malformed. */
  total: number | null;
}

export interface CommentListQuery {
  limit?: number;
  offset?: number;
}

export function commentsPath(complaintId: number, audience: CommentAudience): string {
  return audience === 'staff'
    ? `/staff/complaints/${complaintId}/comments`
    : `/complaints/${complaintId}/comments`;
}

/** GET .../comments — oldest first, paginated with X-Total-Count. */
export async function getCommentsApi(
  complaintId: number,
  audience: CommentAudience,
  query: CommentListQuery = {},
  signal?: AbortSignal,
): Promise<CommentPage> {
  const params = new URLSearchParams();
  params.set('limit', String(query.limit ?? COMMENT_PAGE_SIZE));
  params.set('offset', String(query.offset ?? 0));

  const { data, headers } = await apiRequest<CommentOut[]>(
    `${commentsPath(complaintId, audience)}?${params.toString()}`,
    { signal },
  );

  const rawTotal = headers.get('X-Total-Count');
  return {
    items: Array.isArray(data) ? data : [],
    total: rawTotal !== null && /^\d+$/.test(rawTotal) ? Number(rawTotal) : null,
  };
}

/** POST .../comments — the body is stripped before sending; the server stores the stripped text. */
export function postCommentApi(
  complaintId: number,
  audience: CommentAudience,
  body: string,
  signal?: AbortSignal,
): Promise<CommentOut> {
  return apiFetch<CommentOut>(commentsPath(complaintId, audience), {
    method: 'POST',
    body: { body: body.trim() },
    signal,
  });
}
