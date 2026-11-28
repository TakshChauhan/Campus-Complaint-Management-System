import { expect, test } from '@playwright/test';
import { SEED, storageFor } from './helpers';

test.use({ storageState: storageFor('student') });

test.describe('Raise complaint', () => {
  test('similar text shows the duplicate warning, and the complaint can still be submitted', async ({ page }) => {
    await page.goto('/complaints/new');

    // Close to the seeded open complaint, so the TF-IDF check should match it.
    await page.getByLabel('Complaint title').fill('Projector not working in computer lab 3');
    await page
      .getByLabel('Description')
      .fill('The projector in computer lab 3 shows no signal from any laptop since Monday morning.');

    const warning = page.getByRole('region', { name: 'Possible duplicate complaints warning' });
    await expect(warning).toBeVisible({ timeout: 10_000 });
    await expect(warning.getByText(/Similar complaints already reported/)).toBeVisible();
    await expect(warning.getByText(SEED.openTitle)).toBeVisible();

    await page.getByLabel('Department').selectOption({ label: 'IT Services' });
    await page.getByRole('button', { name: 'Submit complaint' }).click();

    await expect(page.getByText('Complaint reference')).toBeVisible();
    await expect(page.getByRole('link', { name: 'View my complaints' })).toBeVisible();
  });

  test('unrelated text shows no duplicate warning', async ({ page }) => {
    await page.goto('/complaints/new');
    await page.getByLabel('Complaint title').fill('Broken basketball hoop');
    await page.getByLabel('Description').fill('The hoop on the outdoor court is bent and the net is missing.');

    // Give the debounced check time to run before asserting that nothing appeared.
    await page.waitForTimeout(1500);
    await expect(page.getByRole('region', { name: 'Possible duplicate complaints warning' })).toHaveCount(0);
  });
});
