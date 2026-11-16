import { apiFetch } from './client';
import {
  AdminMetricsSummary,
  ResolutionMetricsResponse,
  AdminStaffListItem,
  StaffHostelAssignmentUpdate,
} from '../types';

/**
 * Fetch rolling-average resolution metrics.
 * Backend contract: GET /api/v1/admin/metrics/resolution?window_days=30
 */
export async function getResolutionMetricsApi(
  windowDays = 30,
  departmentId?: number,
  signal?: AbortSignal
): Promise<ResolutionMetricsResponse> {
  const params = new URLSearchParams();
  if (windowDays) params.set('window_days', String(windowDays));
  if (departmentId) params.set('department_id', String(departmentId));
  const qs = params.toString();
  return apiFetch<ResolutionMetricsResponse>(`/admin/metrics/resolution${qs ? `?${qs}` : ''}`, { signal });
}

/**
 * Fetch the comprehensive admin metrics summary (status counts, department breakdown, and resolution metrics).
 * Backend contract: GET /api/v1/admin/metrics/summary
 */
export async function getAdminMetricsSummaryApi(
  signal?: AbortSignal
): Promise<AdminMetricsSummary> {
  return apiFetch<AdminMetricsSummary>('/admin/metrics/summary', { signal });
}




/**
 * Fetch all staff members with their department and assigned hostels.
 * Backend contract: GET /api/v1/admin/staff
 */
export async function getAdminStaffApi(
  signal?: AbortSignal
): Promise<AdminStaffListItem[]> {
  return apiFetch<AdminStaffListItem[]>('/admin/staff', { signal });
}

/**
 * Replace a staff member's assigned hostels.
 * Backend contract: PUT /api/v1/admin/staff/{staff_id}/hostels
 */
export async function updateStaffHostelsApi(
  staffId: number,
  payload: StaffHostelAssignmentUpdate
): Promise<AdminStaffListItem> {
  return apiFetch<AdminStaffListItem>(`/admin/staff/${staffId}/hostels`, {
    method: 'PUT',
    body: payload,
  });
}
