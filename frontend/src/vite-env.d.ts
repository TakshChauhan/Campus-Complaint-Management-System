/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin, e.g. http://localhost:8000 (a trailing /api/v1 is tolerated). */
  readonly VITE_API_BASE_URL?: string;
  /** "true" shows the Google sign-in button. Must match backend GOOGLE_AUTH_ENABLED. */
  readonly VITE_GOOGLE_AUTH_ENABLED?: string;
  /** Comma-separated domains used for the registration hint. The backend is authoritative. */
  readonly VITE_ALLOWED_EMAIL_DOMAINS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
