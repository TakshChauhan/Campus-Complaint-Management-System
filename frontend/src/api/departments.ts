import { apiFetch } from './client';
import { Department, DepartmentSuggestionResponse } from '../types';

export async function getDepartmentsApi(): Promise<Department[]> {
  return await apiFetch<Department[]>('/api/v1/departments', {
    method: 'GET',
  });
}

export async function suggestDepartmentApi(
  title: string,
  description: string
): Promise<DepartmentSuggestionResponse> {
  return await apiFetch<DepartmentSuggestionResponse>('/api/v1/departments/suggest', {
    method: 'POST',
    body: JSON.stringify({ title, description }),
  });
}
