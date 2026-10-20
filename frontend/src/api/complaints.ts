import { apiFetch, apiRequest } from './client';
import {
  ComplaintCreatePayload,
  ComplaintListItem,
  ComplaintListQuery,
  ComplaintPage,
  ComplaintResponse,
} from '../types';

export function createComplaintApi(payload: ComplaintCreatePayload): Promise<ComplaintResponse> {
  return apiFetch<ComplaintResponse>('/complaints', { method: 'POST', body: payload });
}

/** GET /complaints/mine — server-side search, filters and pagination with X-Total-Count. */
export async function getMyComplaintsApi(query: ComplaintListQuery = {}, signal?: AbortSignal): Promise<ComplaintPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const qs = params.toString();
  const { data, headers } = await apiRequest<ComplaintListItem[]>(`/complaints/mine${qs ? `?${qs}` : ''}`, { signal });
  const rawTotal = headers.get('X-Total-Count');
  const total = rawTotal !== null && /^\d+$/.test(rawTotal) ? Number(rawTotal) : null;
  return { items: data, total };
}

export function getMyComplaintApi(id: number, signal?: AbortSignal): Promise<ComplaintResponse> {
  return apiFetch<ComplaintResponse>(`/complaints/${id}`, { signal });
}
