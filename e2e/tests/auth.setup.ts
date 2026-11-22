import { test as setup } from '@playwright/test';
import { ACCOUNTS, signIn, storageFor, type Role } from './helpers';

// Sign in once per role and save the session, so the specs stay under the
// auth rate limit (15 requests per minute per IP).
const roles: Role[] = ['student', 'itStaff', 'warden', 'admin'];

for (const role of roles) {
  setup(`sign in as ${role}`, async ({ page }) => {
    await signIn(page, ACCOUNTS[role]);
    await page.context().storageState({ path: storageFor(role) });
  });
}
