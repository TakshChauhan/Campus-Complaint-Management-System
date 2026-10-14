import { apiFetch } from './client';
import { ComplaintCreatePayload, ComplaintListItem, ComplaintResponse } from '../types';

export async function createComplaintApi(
  payload: ComplaintCreatePayload
): Promise<ComplaintResponse> {
  return await apiFetch<ComplaintResponse>('/api/v1/complaints', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function getMyComplaintsApi(): Promise<ComplaintListItem[]> {
  return await apiFetch<ComplaintListItem[]>('/api/v1/complaints/mine', {
    method: 'GET',
  });
}
