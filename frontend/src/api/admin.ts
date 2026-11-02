import { apiFetch } from './client';
import { AdminMetricsSummary, ResolutionMetricsResponse } from '../types';

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


