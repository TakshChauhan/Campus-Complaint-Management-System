import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import {
  COMMENT_MAX_LENGTH,
  COMMENT_PAGE_SIZE,
  CommentAudience,
  CommentOut,
  getCommentsApi,
  postCommentApi,
} from '../api/comments';
import { ApiClientError, errorMessage } from '../api/client';
import { formatDateTime } from '../lib/format';
import { Alert, Button, Skeleton, TextAreaField } from './ui';

type LoadState = 'loading' | 'ready' | 'not_found' | 'error';

interface ComplaintCommentsProps {
  complaintId: number;
  /** Which route family to use: the student's own complaint, or the staff queue. */
  audience: CommentAudience;
  /** Heading level, so the section fits the page it sits in (h2 on the student page, h3 in the staff panel). */
  headingLevel?: 2 | 3;
  className?: string;
}

/**
 * Who wrote a comment, from the viewer's side: "You" for the viewer's own,
 * otherwise "Staff" or "Student". Anything that is not a student counts as staff.
 */
export function commentAuthorLabel(comment: CommentOut): 'You' | 'Staff' | 'Student' {
  if (comment.is_mine) return 'You';
  return comment.author_role === 'student' ? 'Student' : 'Staff';
}

/** Oldest first. The server already sorts this way; sorting again keeps merged pages in order. */
function sortComments(items: CommentOut[]): CommentOut[] {
  return [...items].sort((a, b) => {
    const diff = Date.parse(a.created_at) - Date.parse(b.created_at);
    return Number.isNaN(diff) || diff === 0 ? a.id - b.id : diff;
  });
}

function mergeComments(existing: CommentOut[], incoming: CommentOut[]): CommentOut[] {
  const byId = new Map<number, CommentOut>();
  for (const comment of existing) byId.set(comment.id, comment);
  for (const comment of incoming) byId.set(comment.id, comment);
  return sortComments([...byId.values()]);
}

function isNotFound(err: unknown): boolean {
  return err instanceof ApiClientError && err.status === 404;
}

export function ComplaintComments({ complaintId, audience, headingLevel = 2, className }: ComplaintCommentsProps) {
  const headingId = useId();
  const Heading = headingLevel === 3 ? 'h3' : 'h2';
  const otherParty = audience === 'staff' ? 'the student' : 'staff';

  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [comments, setComments] = useState<CommentOut[]>([]);
  // The server's X-Total-Count. When it is missing, a full last page means there may be more.
  const [total, setTotal] = useState<number | null>(null);
  const [lastPageFull, setLastPageFull] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);

  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sendingRef = useRef(false);
  const refocusRef = useRef(false);
  // Bumped whenever the thread being shown changes, so a slow reply for the
  // previous complaint can never land in the new one.
  const generationRef = useRef(0);

  const hasMore = total !== null ? comments.length < total : lastPageFull;

  useEffect(() => {
    const controller = new AbortController();
    generationRef.current += 1;
    setLoadState('loading');
    setLoadError(null);
    setComments([]);
    setTotal(null);
    setLastPageFull(false);
    setLoadMoreError(null);
    setLoadingMore(false);
    // A draft written for one complaint must never be posted to another.
    setDraft('');
    setSendError(null);
    setSending(false);
    sendingRef.current = false;

    getCommentsApi(complaintId, audience, { offset: 0 }, controller.signal)
      .then((page) => {
        setComments(sortComments(page.items));
        setTotal(page.total);
        setLastPageFull(page.items.length >= COMMENT_PAGE_SIZE);
        setLoadState('ready');
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        if (isNotFound(err)) {
          setLoadState('not_found');
        } else {
          setLoadError(errorMessage(err, "Couldn't load comments."));
          setLoadState('error');
        }
      });

    return () => controller.abort();
  }, [complaintId, audience, reloadKey]);

  // Disabling the textarea while sending drops its focus; give it back afterwards.
  useEffect(() => {
    if (!sending && refocusRef.current) {
      refocusRef.current = false;
      textareaRef.current?.focus();
    }
  }, [sending]);

  const loadMore = useCallback(async () => {
    if (loadingMore) return;
    const generation = generationRef.current;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const page = await getCommentsApi(complaintId, audience, { offset: comments.length });
      if (generation !== generationRef.current) return;
      setComments((prev) => mergeComments(prev, page.items));
      setTotal(page.total);
      setLastPageFull(page.items.length >= COMMENT_PAGE_SIZE);
    } catch (err) {
      if (generation !== generationRef.current) return;
      if (isNotFound(err)) setLoadState('not_found');
      else setLoadMoreError(errorMessage(err, "Couldn't load more comments."));
    } finally {
      if (generation === generationRef.current) setLoadingMore(false);
    }
  }, [audience, comments.length, complaintId, loadingMore]);

  const trimmed = draft.trim();
  const canSend = trimmed.length > 0 && draft.length <= COMMENT_MAX_LENGTH && !sending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSend || sendingRef.current) return;

    const generation = generationRef.current;
    sendingRef.current = true;
    setSending(true);
    setSendError(null);

    try {
      const created = await postCommentApi(complaintId, audience, trimmed);
      if (generation !== generationRef.current) return;

      if (hasMore) {
        // Earlier pages are not all on screen, so appending would put the new
        // comment in the wrong place. Fetch the next page instead.
        void loadMore();
      } else {
        setComments((prev) => mergeComments(prev, [created]));
        setTotal((prev) => (prev === null ? null : prev + 1));
      }
      setDraft('');
      refocusRef.current = true;
    } catch (err) {
      if (generation !== generationRef.current) return;
      if (isNotFound(err)) {
        setLoadState('not_found');
      } else {
        // The typed text stays in the box so nothing has to be retyped.
        setSendError(errorMessage(err, "Couldn't send your comment. Try again."));
        refocusRef.current = true;
      }
    } finally {
      // If the thread changed meanwhile, the reset effect already cleared this.
      if (generation === generationRef.current) {
        sendingRef.current = false;
        setSending(false);
      }
    }
  }

  const sectionClass = ['comments', className].filter(Boolean).join(' ');
  const titleClass = ['comments__title', headingLevel === 2 && 'detail-section__title'].filter(Boolean).join(' ');

  return (
    <section className={sectionClass} aria-labelledby={headingId}>
      <Heading id={headingId} className={titleClass}>
        Comments
      </Heading>

      {loadState === 'loading' ? (
        <div className="comments__loading" aria-busy="true" aria-label="Loading comments">
          <Skeleton width="100%" height={52} />
          <Skeleton width="100%" height={52} />
        </div>
      ) : loadState === 'not_found' ? (
        <p className="comments__unavailable" role="status">
          Comments aren't available for this complaint. It may have been removed, or you may not have access to it.
        </p>
      ) : loadState === 'error' ? (
        <Alert
          tone="error"
          title="Couldn't load comments"
          action={
            <Button size="sm" variant="secondary" icon="refresh" onClick={() => setReloadKey((k) => k + 1)}>
              Retry
            </Button>
          }
        >
          {loadError}
        </Alert>
      ) : (
        <>
          {comments.length === 0 ? (
            <div className="comments__empty">
              <p className="comments__empty-title">No comments yet</p>
              <p className="comments__empty-text">
                Messages between you and {otherParty} about this complaint will appear here.
              </p>
            </div>
          ) : (
            <ol className="comment-list" aria-label="Comments, oldest first">
              {comments.map((comment) => {
                const label = commentAuthorLabel(comment);
                return (
                  <li key={comment.id} className={`comment comment--${comment.is_mine ? 'mine' : 'other'}`}>
                    <div className="comment__meta">
                      <span className="comment__author">{label}</span>
                      {!comment.is_mine && comment.author_name ? (
                        <span className="comment__name">{comment.author_name}</span>
                      ) : null}
                      <time className="comment__time" dateTime={comment.created_at}>
                        {formatDateTime(comment.created_at)}
                      </time>
                    </div>
                    <p className="comment__body">{comment.body}</p>
                  </li>
                );
              })}
            </ol>
          )}

          {hasMore ? (
            <div className="comments__more">
              {loadMoreError ? (
                <Alert tone="error" title="Couldn't load more comments">
                  {loadMoreError}
                </Alert>
              ) : null}
              <Button size="sm" variant="secondary" loading={loadingMore} onClick={() => void loadMore()}>
                Load more comments
              </Button>
            </div>
          ) : null}

          <form className="comments__form" onSubmit={handleSubmit} noValidate>
            <TextAreaField
              ref={textareaRef}
              label="Add a comment"
              name="comment"
              required
              rows={3}
              maxLength={COMMENT_MAX_LENGTH}
              showCounter
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={sending}
              placeholder={`Write a message to ${otherParty}…`}
              hint="Comments can't be edited or deleted once sent."
            />

            {sendError ? (
              <Alert tone="error" title="Comment not sent">
                {sendError}
              </Alert>
            ) : null}

            <div className="comments__actions">
              <Button type="submit" loading={sending} disabled={!canSend}>
                {sending ? 'Sending…' : 'Post comment'}
              </Button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
