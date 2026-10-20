import { apiFetch } from './client';
import { Department, DepartmentSuggestionResponse } from '../types';

export function getDepartmentsApi(signal?: AbortSignal): Promise<Department[]> {
  return apiFetch<Department[]>('/departments', { signal });
}

/** Keyword-based advisory suggestion (not machine learning). The student always makes the final choice. */
export function suggestDepartmentApi(title: string, description: string): Promise<DepartmentSuggestionResponse> {
  return apiFetch<DepartmentSuggestionResponse>('/departments/suggest', {
    method: 'POST',
    body: { title, description },
  });
}
