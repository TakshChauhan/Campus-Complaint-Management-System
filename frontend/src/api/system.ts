import { apiFetch } from './client';
import { HealthResponse, ReadinessResponse } from '../types';

export function getHealthApi(signal?: AbortSignal): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health', { versioned: false, auth: false, signal });
}

/** 503 is a valid answer here ("not ready"), so it is returned rather than thrown. */
export function getReadinessApi(signal?: AbortSignal): Promise<ReadinessResponse> {
  return apiFetch<ReadinessResponse>('/health/ready', {
    versioned: false,
    auth: false,
    acceptStatuses: [503],
    signal,
  });
}
