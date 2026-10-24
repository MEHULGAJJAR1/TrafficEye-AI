import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 120000,
  expect: { timeout: 15000 },
  reporter: [['list'], ['json', { outputFile: '../docs/browser-tests.json' }]],
  use: { baseURL: process.env.TE_E2E_URL || 'http://127.0.0.1:5173', browserName: 'chromium', viewport: { width: 1440, height: 1050 }, headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  // Start the backend and frontend first. Tests only remove their own created jobs.
});
