import { apiFetch, apiRequest } from './client';
import { FeedItem, FeedListResponse, HostelFeedItem } from '../types';

export interface FeedQueryOptions {
  status?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}

export interface HostelFeedQueryOptions extends FeedQueryOptions {
  hostelId?: number;
}

/**
 * Fetch published complaints for a non-Hostel department.
 * GET /api/v1/feeds/departments/{department_id}
 */
export async function getDepartmentFeedApi(
  departmentId: number,
  options: FeedQueryOptions = {},
): Promise<FeedListResponse<FeedItem>> {
  const params = new URLSearchParams();
  if (options.status) params.set('status', options.status);
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.offset !== undefined) params.set('offset', String(options.offset));

  const qs = params.toString();
  const url = `/feeds/departments/${departmentId}${qs ? `?${qs}` : ''}`;
  const { data, headers } = await apiRequest<FeedItem[]>(url, { signal: options.signal });
  const rawTotal = headers.get('X-Total-Count');
  const total = rawTotal !== null && /^\d+$/.test(rawTotal) ? Number(rawTotal) : data.length;
  return { items: data, total };
}

/**
 * Fetch published HMC/hostel-scoped complaints.
 * GET /api/v1/feeds/hostel
 */
export async function getHostelFeedApi(
  options: HostelFeedQueryOptions = {},
): Promise<FeedListResponse<HostelFeedItem>> {
  const params = new URLSearchParams();
  if (options.hostelId !== undefined && options.hostelId > 0) {
    params.set('hostel_id', String(options.hostelId));
  }
  if (options.status) params.set('status', options.status);
  if (options.limit !== undefined) params.set('limit', String(options.limit));
  if (options.offset !== undefined) params.set('offset', String(options.offset));

  const qs = params.toString();
  const url = `/feeds/hostel${qs ? `?${qs}` : ''}`;
  const { data, headers } = await apiRequest<HostelFeedItem[]>(url, { signal: options.signal });
  const rawTotal = headers.get('X-Total-Count');
  const total = rawTotal !== null && /^\d+$/.test(rawTotal) ? Number(rawTotal) : data.length;
  return { items: data, total };
}

/**
 * Fetch a single public feed complaint item.
 * GET /api/v1/feeds/items/{complaint_id}
 */
export async function getFeedItemDetailApi(
  complaintId: number,
  signal?: AbortSignal,
): Promise<HostelFeedItem> {
  return apiFetch<HostelFeedItem>(`/feeds/items/${complaintId}`, { signal });
}
