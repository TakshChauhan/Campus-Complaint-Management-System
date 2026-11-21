import React, { useState } from 'react';
import { getComplaintFeedbackApi, submitComplaintFeedbackApi } from '../api/feedback';
import { ApiClientError, errorMessage } from '../api/client';
import { ComplaintFeedback } from '../types';
import { Alert, Button, Icon, TextAreaField } from './ui';

export interface FeedbackFormProps {
  complaintId: number;
  initialFeedback?: ComplaintFeedback | null;
  onFeedbackSubmitted?: (feedback: ComplaintFeedback) => void;
  onRefetch?: () => void;
}

export function FeedbackForm({
  complaintId,
  initialFeedback = null,
  onFeedbackSubmitted,
  onRefetch,
}: FeedbackFormProps) {
  const [feedback, setFeedback] = useState<ComplaintFeedback | null>(initialFeedback);
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // If feedback exists (either initially or after submit / 409 refetch), display the rating
  const currentFeedback = feedback ?? initialFeedback;

  if (currentFeedback) {
    return (
      <div className="feedback-box feedback-box--submitted" role="region" aria-label="Resolution feedback">
        <div className="feedback-box__head">
          <span className="feedback-box__icon" aria-hidden="true">
            <Icon name="check" size={20} />
          </span>
          <div>
            <h3 className="feedback-box__title">Feedback recorded</h3>
            <p className="feedback-box__text">Thank you for rating how this complaint was handled.</p>
          </div>
        </div>
        <div className="feedback-display">
          <p className="feedback-rating-statement" data-testid="feedback-rating-statement">
            You rated this {currentFeedback.rating}/5
          </p>
          {currentFeedback.comment ? (
            <p className="feedback-comment-quote" data-testid="feedback-comment-quote">
              "{currentFeedback.comment}"
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;

    if (rating === null) {
      setValidationError('Please select a rating between 1 and 5.');
      return;
    }

    setSubmitting(true);
    setValidationError(null);
    setSubmitError(null);

    try {
      const result = await submitComplaintFeedbackApi(complaintId, {
        rating,
        comment: comment.trim() || undefined,
      });
      setFeedback(result);
      onFeedbackSubmitted?.(result);
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 409) {
        // Conflict: feedback already submitted for this complaint. Refetch!
        try {
          const existing = await getComplaintFeedbackApi(complaintId);
          if (existing) {
            setFeedback(existing);
            onFeedbackSubmitted?.(existing);
          } else {
            onRefetch?.();
          }
        } catch {
          onRefetch?.();
        }
      } else {
        setSubmitError(errorMessage(err, 'Failed to submit feedback.'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="feedback-box" role="region" aria-label="Resolution feedback">
      <div className="feedback-box__head">
        <span className="feedback-box__icon" aria-hidden="true">
          <Icon name="info" size={20} />
        </span>
        <div>
          <h3 className="feedback-box__title">How was your complaint resolved?</h3>
          <p className="feedback-box__text">
            Please rate how this issue was handled to help us improve campus services.
          </p>
        </div>
      </div>

      {submitError ? (
        <Alert tone="error" title="Couldn't submit feedback" className="mb-4">
          {submitError}
        </Alert>
      ) : null}

      <form onSubmit={handleSubmit} className="feedback-form" noValidate>
        <fieldset className="feedback-rating-group" aria-required="true">
          <legend className="field__label">
            Rating <span className="field__required" aria-hidden="true">*</span>
          </legend>
          <div className="feedback-rating-options" role="radiogroup" aria-label="Resolution rating (1 to 5)">
            {[1, 2, 3, 4, 5].map((val) => (
              <label
                key={val}
                htmlFor={`rating-${val}`}
                className={`rating-option ${rating === val ? 'rating-option--selected' : ''}`}
              >
                <input
                  type="radio"
                  id={`rating-${val}`}
                  name="rating"
                  value={val}
                  checked={rating === val}
                  onChange={() => {
                    setRating(val);
                    setValidationError(null);
                  }}
                  disabled={submitting}
                  aria-label={`${val} star${val > 1 ? 's' : ''}`}
                />
                <span aria-hidden="true">{val}</span>
              </label>
            ))}
          </div>
          {validationError ? (
            <p className="field__error" id="rating-error">
              <Icon name="alert" size={16} />
              {validationError}
            </p>
          ) : null}
        </fieldset>

        <TextAreaField
          label="Comments"
          name="comment"
          placeholder="Optional comment about the resolution process..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={500}
          showCounter={true}
          rows={3}
          disabled={submitting}
          hint="Optional feedback up to 500 characters."
        />

        <div className="feedback-form__actions">
          <Button
            type="submit"
            variant="primary"
            loading={submitting}
            disabled={submitting}
          >
            Submit feedback
          </Button>
        </div>
      </form>
    </div>
  );
}
