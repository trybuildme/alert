// Playwright configuration for NOAH end-to-end tests.
//
// Strategy: run the real Vite dev server, then intercept every backend
// touchpoint (/api/**, /tiles) with page.route fixtures. This keeps E2E
// hermetic — no backend, ingest workers or external hazard feeds
// required — while still exercising the full React/map UI shell.

import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3010',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3010',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
