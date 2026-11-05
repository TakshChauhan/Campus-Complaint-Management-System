import { apiFetch } from './client';
import { CoverageGapItem } from '../types';

export function getCoverageGapsApi(signal?: AbortSignal): Promise<CoverageGapItem[]> {
  return apiFetch<CoverageGapItem[]>('/admin/coverage-gaps', { signal });
}
