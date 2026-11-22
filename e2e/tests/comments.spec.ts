import { expect, test, type Page } from '@playwright/test';
import { SEED, storageFor } from './helpers';

// Needs S5-05 (comments API, #115) and S5-06 (comments UI, #123).

const STUDENT_MESSAGE = 'Is there an update on the projector?';
const STAFF_REPLY = 'A technician is booked for Tuesday morning.';

const thread = (page: Page) => page.getByRole('list', { name: 'Comments, oldest first' });

test.describe('Complaint comments', () => {
  test('student and handling staff exchange comments on a complaint', async ({ browser }) => {
    const studentContext = await browser.newContext({ storageState: storageFor('student') });
    const staffContext = await browser.newContext({ storageState: storageFor('itStaff') });
    const student = await studentContext.newPage();
    const staff = await staffContext.newPage();

    // 1. Student opens their complaint: no comments yet, then posts one.
    await student.goto('/complaints');
    await student.getByText(SEED.openTitle, { exact: true }).click();
    await expect(student.getByText('No comments yet')).toBeVisible();

    const post = student.getByRole('button', { name: 'Post comment' });
    await student.getByLabel('Add a comment').fill(`   ${STUDENT_MESSAGE}   `);
    await post.click();
    const studentItem = thread(student).getByRole('listitem').filter({ hasText: STUDENT_MESSAGE });
    await expect(studentItem).toBeVisible();
    await expect(studentItem.getByText('You', { exact: true })).toBeVisible();

    // 2. Staff in the handling department see it, labelled Student with the name, and reply.
    await staff.goto('/staff');
    await staff.getByRole('button', { name: new RegExp(SEED.openTitle) }).first().click();
    const fromStudent = thread(staff).getByRole('listitem').filter({ hasText: STUDENT_MESSAGE });
    await expect(fromStudent).toBeVisible();
    await expect(fromStudent.getByText('Student', { exact: true })).toBeVisible();
    await expect(fromStudent.getByText('E2E Student')).toBeVisible();

    await staff.getByLabel('Add a comment').fill(STAFF_REPLY);
    await staff.getByRole('button', { name: 'Post comment' }).click();
    await expect(thread(staff).getByRole('listitem').filter({ hasText: STAFF_REPLY })).toBeVisible();

    // 3. Student sees the reply after a reload, oldest first, labelled Staff.
    await student.reload();
    const items = thread(student).getByRole('listitem');
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toContainText(STUDENT_MESSAGE);
    await expect(items.nth(1)).toContainText(STAFF_REPLY);
    await expect(items.nth(1).getByText('Staff', { exact: true })).toBeVisible();
    await expect(items.nth(1).getByText('E2E IT Staff')).toBeVisible();

    // End both pages on the thread so the run's screenshots show it.
    await thread(student).scrollIntoViewIfNeeded();
    await thread(staff).scrollIntoViewIfNeeded();

    await studentContext.close();
    await staffContext.close();
  });

  test('a blank comment cannot be posted', async ({ browser }) => {
    const context = await browser.newContext({ storageState: storageFor('student') });
    const page = await context.newPage();
    await page.goto('/complaints');
    await page.getByText(SEED.resolvedTitle, { exact: true }).click();

    await page.getByLabel('Add a comment').fill('     ');
    await expect(page.getByRole('button', { name: 'Post comment' })).toBeDisabled();
    await context.close();
  });
});
