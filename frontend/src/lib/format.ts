/** Presentation helpers shared across pages. */

/** Display reference for a backend complaint ID. The ID itself always comes from the API. */
export function complaintReference(id: number): string {
  return `CMP-${id}`;
}

const dateTimeFormatter = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

const dateFormatter = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'Unknown date';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? 'Unknown date' : dateTimeFormatter.format(date);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'Unknown date';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? 'Unknown date' : dateFormatter.format(date);
}

/** Human label for the persisted complaint status string. Unknown values are shown as-is. */
export function statusLabel(status: string): string {
  const known: Record<string, string> = {
    submitted: 'Submitted',
    in_progress: 'In progress',
    resolved: 'Resolved',
    rejected: 'Rejected',
    closed: 'Closed',
    reopened: 'Reopened',
  };
  return known[status] ?? status.replace(/_/g, ' ');
}

export function firstName(fullName: string | undefined | null): string {
  const trimmed = (fullName ?? '').trim();
  return trimmed ? trimmed.split(/\s+/)[0] : '';
}

export const ROLE_LABELS = {
  student: 'Student',
  staff: 'Staff',
  admin: 'Administrator',
} as const;

export function formatSimilarityScore(score: number): string {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  return pct + "%";
}
