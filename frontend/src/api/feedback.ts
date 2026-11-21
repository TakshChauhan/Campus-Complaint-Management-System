import { apiFetch } from './client';
import { ComplaintFeedback, SubmitFeedbackPayload } from '../types';

/**
 * Fetch feedback for a complaint (owner only).
 * Backend contract 7.17: GET /api/v1/complaints/{id}/feedback
 */
export async function getComplaintFeedbackApi(
  complaintId: number,
  signal?: AbortSignal
): Promise<ComplaintFeedback | null> {
  return apiFetch<ComplaintFeedback | null>(`/complaints/${complaintId}/feedback`, { signal });
}

/**
 * Submit feedback for a resolved complaint (owner only, once per complaint).
 * Backend contract 7.17: POST /api/v1/complaints/{id}/feedback
 */
export async function submitComplaintFeedbackApi(
  complaintId: number,
  payload: SubmitFeedbackPayload,
  signal?: AbortSignal
): Promise<ComplaintFeedback> {
  return apiFetch<ComplaintFeedback>(`/complaints/${complaintId}/feedback`, {
    method: 'POST',
    body: payload,
    signal,
  });
}
