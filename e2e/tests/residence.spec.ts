import { expect, test } from '@playwright/test';
import { SEED, storageFor } from './helpers';

test.describe('Residence declaration and verification', () => {
  test('student declares a residence, Hostel staff approve it, student sees Verified', async ({ browser }) => {
    const studentContext = await browser.newContext({ storageState: storageFor('student') });
    const wardenContext = await browser.newContext({ storageState: storageFor('warden') });
    const student = await studentContext.newPage();
    const warden = await wardenContext.newPage();

    // 1. Student declares.
    await student.goto('/profile');
    await student.getByRole('button', { name: 'Declare residence' }).click();
    await student.getByLabel('Hostel building').selectOption({ label: SEED.hostel });
    await student.getByLabel('Wing / Block').selectOption({ label: SEED.wing });
    await student.getByLabel('Floor').selectOption({ label: SEED.floor });
    await student.getByRole('button', { name: 'Save residence' }).click();
    await expect(student.getByText('Verification pending')).toBeVisible();

    // 2. Hostel staff assigned to that hostel approve it.
    await warden.goto('/staff');
    await expect(warden.getByText('Residence verification queue')).toBeVisible();
    await expect(warden.getByText('e2e.student@dau.ac.in')).toBeVisible();
    await warden.getByRole('button', { name: 'Approve residence' }).first().click();
    await expect(warden.getByText('Decision submitted')).toBeVisible();

    // 3. Student sees the result.
    await student.reload();
    await expect(student.getByText('Verified').first()).toBeVisible();

    await studentContext.close();
    await wardenContext.close();
  });
});
