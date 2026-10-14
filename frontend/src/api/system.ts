import { apiFetch } from './client';
import { HealthResponse } from '../types';

export async function getHealthApi(): Promise<HealthResponse> {
  return await apiFetch<HealthResponse>('/health', {
    method: 'GET',
  });
}
