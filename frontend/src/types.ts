// TypeScript Interfaces matching the CCMS FastAPI backend schema contracts

export type UserRole = 'student' | 'staff' | 'admin';

export interface UserSafeResponse {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  department_id: number | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: UserSafeResponse;
}

export interface Department {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
}

export interface DepartmentSuggestionItem {
  department_id: number;
  department_name: string;
  confidence_score: number; // e.g. 0.88 -> 88%
  rationale?: string;
}

export interface DepartmentSuggestionResponse {
  status: string;
  version: string;
  suggestions: DepartmentSuggestionItem[];
  disclaimer: string;
}

export interface ComplaintCreatePayload {
  title: string;
  description: string;
  department_id: number;
}

export interface ComplaintResponse {
  id: number;
  title: string;
  description: string;
  department_id: number;
  department_name: string;
  created_by_id: number;
  status: string;
  created_at: string;
}

export interface ComplaintListItem {
  id: number;
  title: string;
  department_name: string;
  status: string;
  created_at: string;
}

export interface HealthResponse {
  status: string;
  project: string;
  version: string;
  environment: string;
  database: string;
}

export interface ApiValidationErrorItem {
  field: string;
  message: string;
  type?: string;
}
