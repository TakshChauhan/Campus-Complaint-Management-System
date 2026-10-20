// TypeScript interfaces matching the CCMS FastAPI backend schema contracts (docs/API_CONTRACT.md)

export type UserRole = 'student' | 'staff' | 'admin';

export interface UserSafeResponse {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  email_verified: boolean;
  email_verified_at: string | null;
  email_verification_required?: boolean;
  google_linked?: boolean;
  message?: string | null;
  department_id: number | null;
  created_at: string;
}

export interface GoogleLinkExchangeResponse {
  message: string;
  user: UserSafeResponse;
}

export interface GoogleLinkStatusResponse {
  linked: boolean;
  email: string | null;
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
  confidence_score: number;
  rationale?: string | null;
}

export type SuggestionStatus = 'provisional_advisory' | 'uncertain' | 'error_fallback';

export interface DepartmentSuggestionResponse {
  status: SuggestionStatus;
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
  description_preview: string;
  department_id: number;
  department_name: string;
  status: string;
  created_at: string;
}

export interface ComplaintListQuery {
  limit?: number;
  offset?: number;
  q?: string;
  department_id?: number;
  date_from?: string;
  date_to?: string;
  sort?: 'newest' | 'oldest';
}

export interface ComplaintPage {
  items: ComplaintListItem[];
  /** Total matching complaints from the X-Total-Count header; null if the server did not send it. */
  total: number | null;
}

export interface HealthResponse {
  status: string;
  project: string;
  version: string;
  environment: string;
  database: string;
}

export interface ReadinessResponse {
  ready: boolean;
  database: string;
}

export interface ApiValidationErrorItem {
  field: string;
  message: string;
  type?: string;
}
