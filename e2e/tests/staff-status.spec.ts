import { expect, test } from '@playwright/test';
import { SEED, storageFor } from './helpers';

test.describe('Staff status update', () => {
  test.use({ storageState: storageFor('itStaff') });

  test('department staff move a complaint to in progress with a remark', async ({ page }) => {
    await page.goto('/staff');
    await expect(page.getByText('Department complaint queue')).toBeVisible();

    await page.getByRole('button', { name: new RegExp(SEED.openTitle) }).first().click();
    await expect(page.getByRole('heading', { name: 'Update complaint status' })).toBeVisible();

    const save = page.getByRole('button', { name: 'Save status update' });
    await expect(save).toBeDisabled(); // a remark is required

    await page.getByLabel('New status').selectOption('in_progress');
    await page.getByLabel('Remark (required)').fill('Technician booked for Tuesday.');
    await save.click();

    await expect(page.getByText('Complaint status updated successfully.')).toBeVisible();
  });

});

test.describe('Staff department scope', () => {
  test.use({ storageState: storageFor('warden') });

  test('Hostel staff do not see an IT Services complaint', async ({ page }) => {
    await page.goto('/staff');
    await expect(page.getByText('Department complaint queue')).toBeVisible();
    await expect(page.getByText(SEED.openTitle, { exact: true })).toHaveCount(0);
  });
});
