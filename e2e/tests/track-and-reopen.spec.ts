import { expect, test } from '@playwright/test';
import { SEED, storageFor } from './helpers';

test.use({ storageState: storageFor('student') });

test.describe('Student tracking and reopen', () => {
  test('my complaints lists the seeded complaints and search narrows them', async ({ page }) => {
    await page.goto('/complaints');
    await expect(page.getByText(SEED.openTitle)).toBeVisible();
    await expect(page.getByText(SEED.resolvedTitle)).toBeVisible();

    await page.getByLabel('Search your complaints').fill('projector');
    await expect(page.getByText(SEED.openTitle)).toBeVisible();
    await expect(page.getByText(SEED.resolvedTitle)).toHaveCount(0);
  });

  test('a resolved complaint can be reopened with a reason', async ({ page }) => {
    await page.goto('/complaints');
    await page.getByText(SEED.resolvedTitle).click();
    await expect(page).toHaveURL(/\/complaints\/\d+$/);

    await page.getByRole('button', { name: 'Reopen complaint' }).click();
    await page.getByLabel('Reason for reopening (optional)').fill('Still disconnecting after the fix.');
    await page.getByRole('button', { name: 'Confirm reopen' }).click();

    await expect(page.getByText('Reopened', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reopen complaint' })).toHaveCount(0);
  });
});
