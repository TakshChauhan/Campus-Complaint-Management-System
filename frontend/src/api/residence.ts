import { apiFetch, apiRequest } from './client';
import { MyResidence, ResidenceUpdatePayload } from '../types';

/**
 * Fetch the authenticated student's declared hostel residence and verification status.
 * Endpoint: GET /api/v1/users/me/residence
 * Returns null if the student has not declared a residence yet (HTTP 404).
 */
export async function getMyResidenceApi(signal?: AbortSignal): Promise<MyResidence | null> {
  const result = await apiRequest<MyResidence>('/users/me/residence', {
    method: 'GET',
    acceptStatuses: [404],
    signal,
  });

  if (result.status === 404) {
    return null;
  }

  return result.data;
}

/**
 * Declare or update the student's hostel residence by selecting a floor.
 * Note: Submitting resets verification status to 'pending' and clears any prior rejection remark.
 * Endpoint: PATCH /api/v1/users/me/residence
 */
export async function updateMyResidenceApi(floorId: number): Promise<MyResidence> {
  const payload: ResidenceUpdatePayload = { floor_id: floorId };
  return apiFetch<MyResidence>('/users/me/residence', {
    method: 'PATCH',
    body: payload,
  });
}

