
import { apiFetch, apiRequest } from './client';

export type StaffComplaintStatus =
  | 'submitted'
  | 'in_progress'
  | 'resolved'
  | 'reopened';


export interface StaffComplaintQueueItem {
  id: number;
  title: string;
  description_preview: string;
  department_id: number;
  department_name: string;
  status: string;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;

  // Sprint 3 S3-24: complaint location
  hostel?: string | null;
  wing?: string | null;
  floor?: string | null;
}


export interface StaffComplaintDetail {
  id: number;
  title: string;
  description: string;
  department_id: number;
  department_name: string;
  status: string;
  is_public: boolean;
  hostel: string | null;
  wing: string | null;
  floor: string | null;
  reopen_count: number;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface ComplaintStatusHistoryItem {
  id: number;
  from_status: string | null;
  to_status: string;
  actor_id: number;
  remark: string | null;
  created_at: string;
}

export interface StaffComplaintQuery {
  status?: StaffComplaintStatus;
  hostel?: string;
  limit?: number;
  offset?: number;
}

export interface StaffComplaintPage {
  items: StaffComplaintQueueItem[];
  total: number | null;
}

export async function getStaffComplaintsApi(
  query: StaffComplaintQuery = {},
  signal?: AbortSignal,
): Promise<StaffComplaintPage> {
  const params = new URLSearchParams();

  if (query.status) params.set('status', query.status);
  if (query.hostel) params.set('hostel', query.hostel);
  params.set('limit', String(query.limit ?? 50));
  params.set('offset', String(query.offset ?? 0));

  const { data, headers } = await apiRequest<StaffComplaintQueueItem[]>(
    `/staff/complaints?${params.toString()}`,
    { signal },
  );

  const rawTotal = headers.get('X-Total-Count');

  return {
    items: data,
    total: rawTotal !== null && /^\d+$/.test(rawTotal)
      ? Number(rawTotal)
      : null,
  };
}

export function getStaffComplaintApi(
  id: number,
  signal?: AbortSignal,
): Promise<StaffComplaintDetail> {
  return apiFetch<StaffComplaintDetail>(
    `/staff/complaints/${id}`,
    { signal },
  );
}

export function getComplaintHistoryApi(
  id: number,
  signal?: AbortSignal,
): Promise<ComplaintStatusHistoryItem[]> {
  return apiFetch<ComplaintStatusHistoryItem[]>(
    `/complaints/${id}/history`,
    { signal },
  );
}

export function updateStaffComplaintStatusApi(
  id: number,
  status: 'in_progress' | 'resolved',
  remark: string,
): Promise<StaffComplaintDetail> {
  return apiFetch<StaffComplaintDetail>(
    `/staff/complaints/${id}/status`,
    {
      method: 'PATCH',
      body: { status, remark },
    },
  );
}
