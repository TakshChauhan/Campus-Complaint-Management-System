import { expect, test } from '@playwright/test';
import { ACCOUNTS, PASSWORD, signIn } from './helpers';

test.describe('Login and register', () => {
  test('a new student can register and is sent to sign in', async ({ page }) => {
    await page.goto('/register');
    await page.getByLabel('Full name').fill('E2E Newcomer');
    await page.getByLabel('University email').fill(`e2e.new.${Date.now()}@dau.ac.in`);
    await page.getByLabel('Password', { exact: true }).fill(PASSWORD);
    await page.getByLabel('Confirm password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Create account' }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText('Account created! Check your inbox')).toBeVisible();
  });

  test('a wrong password keeps the user on the sign-in page', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('University email').fill(ACCOUNTS.student);
    await page.getByLabel('Password', { exact: true }).fill('not-the-password');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();

    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test('a signed-in student lands on the student dashboard', async ({ page }) => {
    await signIn(page, ACCOUNTS.student);
    await expect(page).toHaveURL(/\/dashboard/);
  });
});
