import { expect, test } from '@playwright/test';
import { SEED, storageFor } from './helpers';

test.use({ storageState: storageFor('admin') });

test.describe('Admin staff hostel assignment', () => {
  test('admin assigns a hostel to a Hostel staff member', async ({ page }) => {
    await page.goto('/admin');

    const card = page.getByRole('article', { name: 'Hostel assignments for E2E New Warden' });
    await expect(card).toBeVisible();

    const checkbox = card.getByLabel(`Assign ${SEED.hostel} to E2E New Warden`);
    await expect(checkbox).not.toBeChecked();
    await checkbox.check();
    await card.getByRole('button', { name: 'Save assignments' }).click();

    await expect(page.getByText('Hostel assignments updated for E2E New Warden.')).toBeVisible();

    await page.reload();
    const savedCard = page.getByRole('article', { name: 'Hostel assignments for E2E New Warden' });
    await expect(savedCard.getByLabel(`Assign ${SEED.hostel} to E2E New Warden`)).toBeChecked();
    await expect(savedCard.getByText(`Currently assigned: ${SEED.hostel}`)).toBeVisible();
    // End on the saved card so the run's screenshot shows the result.
    await savedCard.scrollIntoViewIfNeeded();
  });

  test('the coverage gaps panel is shown', async ({ page }) => {
    await page.goto('/admin');
    await expect(page.getByText(/Hostel coverage gaps/)).toBeVisible();
  });
});
