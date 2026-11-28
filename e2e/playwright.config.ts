import { defineConfig, devices } from '@playwright/test';

/**
 * S5-35 GUI tests.
 *
 * Default: starts the backend on a fresh SQLite database (scripts/start-backend.sh)
 * and the Vite dev server, so every run begins from the same seeded data.
 *
 * Against staging: set E2E_BASE_URL (the Vercel URL). No local servers are
 * started then, and the staging database must contain the seed accounts.
 */
const API_PORT = process.env.E2E_API_PORT ?? '8010';
const WEB_PORT = process.env.E2E_WEB_PORT ?? '5180';
const remote = Boolean(process.env.E2E_BASE_URL);
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${WEB_PORT}`;

export default defineConfig({
  testDir: './tests',
  // Tests share one seeded database and the auth rate limit (15 sign-ins/min), so run them in order.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'on',
  },
  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
      use: { channel: process.env.E2E_BROWSER_CHANNEL || undefined },
    },
    {
      name: 'chromium',
      // E2E_BROWSER_CHANNEL=chrome uses the installed Google Chrome instead of
      // Playwright's bundled Chromium (useful when `playwright install` is blocked).
      use: { ...devices['Desktop Chrome'], channel: process.env.E2E_BROWSER_CHANNEL || undefined },
      dependencies: ['setup'],
    },
  ],
  webServer: remote
    ? undefined
    : [
        {
          command: './scripts/start-backend.sh',
          url: `http://127.0.0.1:${API_PORT}/health/ready`,
          reuseExistingServer: false,
          timeout: 120_000,
          env: { E2E_API_PORT: API_PORT, E2E_WEB_PORT: WEB_PORT },
        },
        {
          command: `npm --prefix ../frontend run dev -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
          url: baseURL,
          reuseExistingServer: false,
          timeout: 120_000,
          env: { VITE_API_BASE_URL: `http://127.0.0.1:${API_PORT}` },
        },
      ],
});
