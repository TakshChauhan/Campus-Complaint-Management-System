import { apiFetch } from './client';
import { HostelNode } from '../types';

/**
 * Fetch the active physical hostel hierarchy (Hostel -> Wing -> Floor).
 * Endpoint: GET /api/v1/locations/hostels
 */
export async function getHostelLocationsApi(signal?: AbortSignal): Promise<HostelNode[]> {
  return apiFetch<HostelNode[]>('/locations/hostels', { signal });
}

