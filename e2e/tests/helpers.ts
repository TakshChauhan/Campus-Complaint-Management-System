import { expect, type Page } from '@playwright/test';

/** Test-only password set by seed_e2e.py (E2E_PASSWORD overrides both). */
export const PASSWORD = process.env.E2E_PASSWORD ?? 'E2e-Only-Passw0rd!';

export const ACCOUNTS = {
  student: 'e2e.student@dau.ac.in',
  itStaff: 'e2e.it.staff@dau.ac.in',
  warden: 'e2e.warden@dau.ac.in',
  newWarden: 'e2e.new.warden@dau.ac.in',
  admin: 'e2e.admin@dau.ac.in',
} as const;

export type Role = 'student' | 'itStaff' | 'warden' | 'admin';

/** Saved browser session per role, written by auth.setup.ts. */
export const storageFor = (role: Role) => `.auth/${role}.json`;

/** Must match seed_e2e.py. */
export const SEED = {
  openTitle: 'Projector not working in lab 3',
  resolvedTitle: 'Wi-Fi drops in library reading room',
  hostel: 'E2E Hostel',
  wing: 'Wing A',
  floor: 'Floor 1',
} as const;

export async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto('/login');
  await page.getByLabel('University email').fill(email);
  await page.getByLabel(/^Password\b/).fill(password);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
}
