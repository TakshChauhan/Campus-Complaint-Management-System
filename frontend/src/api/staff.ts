
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

// ---------------------------------------------------------------- Residence Verification (Sprint 3 S3-23)

export type ResidenceStatus = 'pending' | 'verified' | 'rejected';

export interface StaffResidenceItem {
  id: number;
  student_id: number;
  student_name: string;
  student_email: string;
  floor_id: number;
  hostel: string;
  wing: string;
  floor: string;
  status: ResidenceStatus;
  remark: string | null;
  submitted_at: string;
  decided_at: string | null;
}

export interface StaffResidenceQuery {
  status?: ResidenceStatus;
  limit?: number;
  offset?: number;
}

export interface StaffResidencePage {
  items: StaffResidenceItem[];
  total: number | null;
}

export interface ResidenceDecisionPayload {
  decision: 'approve' | 'reject';
  remark?: string;
}

/**
 * Fetch student residence declarations for Hostel staff / admin review.
 * Server sends items and total count in the X-Total-Count header.
 */
export async function getStaffResidencesApi(
  query: StaffResidenceQuery = {},
  signal?: AbortSignal,
): Promise<StaffResidencePage> {
  const params = new URLSearchParams();

  if (query.status) params.set('status', query.status);
  params.set('limit', String(query.limit ?? 20));
  params.set('offset', String(query.offset ?? 0));

  const { data, headers } = await apiRequest<StaffResidenceItem[]>(
    `/staff/residences?${params.toString()}`,
    { signal },
  );

  const rawTotal = headers.get('X-Total-Count');

  return {
    items: data,
    total: rawTotal !== null && /^\d+$/.test(rawTotal) ? Number(rawTotal) : null,
  };
}

/**
 * Approve or reject a student's residence declaration.
 * - 'approve': remark is optional.
 * - 'reject': remark is required (1-2000 chars).
 */
export function decideStaffResidenceApi(
  residenceId: number,
  payload: ResidenceDecisionPayload,
): Promise<StaffResidenceItem> {
  return apiFetch<StaffResidenceItem>(
    `/staff/residences/${residenceId}/decision`,
    {
      method: 'POST',
      body: payload,
    },
  );
}
