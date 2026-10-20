/** Frontend runtime configuration derived from Vite env variables. */

export const GOOGLE_AUTH_ENABLED = import.meta.env.VITE_GOOGLE_AUTH_ENABLED === 'true';

export const ALLOWED_EMAIL_DOMAINS: string[] = (import.meta.env.VITE_ALLOWED_EMAIL_DOMAINS || 'dau.ac.in,daiict.ac.in')
  .split(',')
  .map((d) => d.trim().toLowerCase().replace(/^@/, ''))
  .filter(Boolean);

/** Client-side hint only; the backend enforces the real policy. */
export function isAllowedEmailDomain(email: string): boolean {
  if (ALLOWED_EMAIL_DOMAINS.length === 0 || ALLOWED_EMAIL_DOMAINS.includes('*')) return true;
  const domain = email.trim().toLowerCase().split('@')[1] ?? '';
  return ALLOWED_EMAIL_DOMAINS.some((d) => domain === d || domain.endsWith(`.${d}`));
}

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Limits mirrored from backend Pydantic schemas (backend/app/schemas). */
export const LIMITS = {
  nameMin: 2,
  nameMax: 100,
  passwordMin: 8,
  passwordMaxBytes: 72,
  titleMin: 3,
  titleMax: 120,
  descriptionMin: 10,
  descriptionMax: 2000,
} as const;
