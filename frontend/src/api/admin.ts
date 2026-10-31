import { apiFetch, apiRequest, ApiClientError } from './client';
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
  try {
    return await apiFetch<AdminMetricsSummary>('/admin/metrics/summary', { signal });
  } catch (err) {
    if (signal?.aborted) throw err;
    // If /admin/metrics/summary route returns 404/501 or is pending server deployment,
    // attempt resolution metrics fallback or rethrow
    if (err instanceof ApiClientError && (err.status === 404 || err.status === 501)) {
      try {
        const resolution = await getResolutionMetricsApi(30, undefined, signal);
        return {
          total_complaints: resolution.resolved_count,
          status_counts: [
            { status: 'resolved', count: resolution.resolved_count },
          ],
          department_counts: [],
          resolution_metrics: resolution,
        };
      } catch {
        throw err;
      }
    }
    throw err;
  }
}

