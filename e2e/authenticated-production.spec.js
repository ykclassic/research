const { test, expect } = require('@playwright/test');

const APP_URL = process.env.TEST_APP_URL;
const API_URL = process.env.TEST_API_URL;
const EMAIL = process.env.TEST_EMAIL;
const PASSWORD = process.env.TEST_PASSWORD;

test.describe('authenticated production research', () => {
  test.beforeAll(() => {
    for (const [name, value] of Object.entries({ TEST_APP_URL: APP_URL, TEST_API_URL: API_URL, TEST_EMAIL: EMAIL, TEST_PASSWORD: PASSWORD })) {
      if (!value) throw new Error(`${name} is required`);
    }
  });

  test('login, authenticated API session, research history and protected logout', async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
    await page.getByLabel('Email').fill(EMAIL);
    await page.getByLabel('Password').fill(PASSWORD);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByText(EMAIL, { exact: true })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole('heading', { name: 'Market Research' })).toBeVisible();

    const session = await page.evaluate(async (apiUrl) => {
      const response = await fetch(`${apiUrl}/api/auth/me`, { credentials: 'include' });
      return { status: response.status, body: response.ok ? await response.json() : null };
    }, API_URL);
    expect(session.status).toBe(200);
    expect(session.body.email).toBe(EMAIL);

    const history = await page.evaluate(async (apiUrl) => {
      const response = await fetch(`${apiUrl}/api/research-history?limit=10`, { credentials: 'include' });
      return { status: response.status, body: response.ok ? await response.json() : null };
    }, API_URL);
    expect(history.status).toBe(200);
    expect(Array.isArray(history.body.items)).toBeTruthy();

    await page.getByRole('button', { name: 'Sign out' }).click();
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible({ timeout: 10_000 });

    const afterLogout = await page.evaluate(async (apiUrl) => {
      const response = await fetch(`${apiUrl}/api/auth/me`, { credentials: 'include' });
      return response.status;
    }, API_URL);
    expect(afterLogout).toBe(401);
  });
});
